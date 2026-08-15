# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for platform utilities."""

from unittest.mock import patch
from src.procexec.utils.platform import get_platform, is_windows, is_unix


class TestGetPlatform:
    """Tests for get_platform function."""

    @patch("platform.system")
    def test_get_platform_windows(self, mock_system):
        """Test platform detection on Windows."""
        mock_system.return_value = "Windows"
        result = get_platform()
        assert result == "windows"

    @patch("platform.system")
    def test_get_platform_linux(self, mock_system):
        """Test platform detection on Linux."""
        mock_system.return_value = "Linux"
        result = get_platform()
        assert result == "unix"

    @patch("platform.system")
    def test_get_platform_darwin(self, mock_system):
        """Test platform detection on macOS."""
        mock_system.return_value = "Darwin"
        result = get_platform()
        assert result == "unix"

    @patch("platform.system")
    def test_get_platform_freebsd(self, mock_system):
        """Test platform detection on FreeBSD."""
        mock_system.return_value = "FreeBSD"
        result = get_platform()
        assert result == "unix"

    @patch("platform.system")
    def test_get_platform_unknown(self, mock_system):
        """Test platform detection on unknown system."""
        mock_system.return_value = "UnknownOS"
        result = get_platform()
        # Should default to unix for unknown systems
        assert result == "unix"


class TestIsWindows:
    """Tests for is_windows function."""

    @patch("platform.system")
    def test_is_windows_on_windows(self, mock_system):
        """Test is_windows returns True on Windows."""
        mock_system.return_value = "Windows"
        assert is_windows() is True

    @patch("platform.system")
    def test_is_windows_on_linux(self, mock_system):
        """Test is_windows returns False on Linux."""
        mock_system.return_value = "Linux"
        assert is_windows() is False

    @patch("platform.system")
    def test_is_windows_on_darwin(self, mock_system):
        """Test is_windows returns False on macOS."""
        mock_system.return_value = "Darwin"
        assert is_windows() is False


class TestIsUnix:
    """Tests for is_unix function."""

    @patch("platform.system")
    def test_is_unix_on_linux(self, mock_system):
        """Test is_unix returns True on Linux."""
        mock_system.return_value = "Linux"
        assert is_unix() is True

    @patch("platform.system")
    def test_is_unix_on_darwin(self, mock_system):
        """Test is_unix returns True on macOS."""
        mock_system.return_value = "Darwin"
        assert is_unix() is True

    @patch("platform.system")
    def test_is_unix_on_freebsd(self, mock_system):
        """Test is_unix returns True on FreeBSD."""
        mock_system.return_value = "FreeBSD"
        assert is_unix() is True

    @patch("platform.system")
    def test_is_unix_on_windows(self, mock_system):
        """Test is_unix returns False on Windows."""
        mock_system.return_value = "Windows"
        assert is_unix() is False


class TestPlatformConsistency:
    """Tests for consistency between platform functions."""

    @patch("platform.system")
    def test_windows_and_unix_mutually_exclusive(self, mock_system):
        """Test that is_windows and is_unix are mutually exclusive."""
        # On Windows
        mock_system.return_value = "Windows"
        assert is_windows() is True
        assert is_unix() is False

        # On Linux
        mock_system.return_value = "Linux"
        assert is_windows() is False
        assert is_unix() is True

    @patch("platform.system")
    def test_get_platform_matches_is_functions(self, mock_system):
        """Test that get_platform results match is_* functions."""
        # On Windows
        mock_system.return_value = "Windows"
        assert get_platform() == "windows"
        assert is_windows() is True

        # On Linux
        mock_system.return_value = "Linux"
        assert get_platform() == "unix"
        assert is_unix() is True
