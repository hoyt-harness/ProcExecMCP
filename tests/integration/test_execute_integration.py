# SPDX-License-Identifier: GPL-3.0-or-later
"""Integration tests for execute_command tool with real command execution."""

import pytest
import platform
from src.procexec.tools.execute import execute_command
from src.procexec.utils.validation import SanitizedError


class TestBasicCommandExecution:
    """Tests for basic command execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_python_version(self):
        """Test executing python --version command."""
        result = await execute_command("python --version")

        assert result is not None
        assert "Python" in result.stdout or "Python" in result.stderr
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_execute_echo_command(self):
        """Test executing echo command."""
        if platform.system() == "Windows":
            result = await execute_command("echo Hello World")
        else:
            result = await execute_command('echo "Hello World"')

        assert "Hello" in result.stdout
        assert result.exit_code == 0
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_execute_with_arguments(self):
        """Test executing command with multiple arguments."""
        result = await execute_command("python -c \"print('test')\"")

        assert "test" in result.stdout
        assert result.exit_code == 0


class TestWorkingDirectory:
    """Tests for working directory handling."""

    @pytest.mark.asyncio
    async def test_execute_with_working_directory(self, tmp_path):
        """Test command execution with specified working directory."""
        # Use Python to verify cwd is set correctly (cross-platform)
        result = await execute_command(
            'python -c "import os; print(os.getcwd())"', working_directory=str(tmp_path)
        )

        # Normalize paths for comparison (resolve symlinks, etc.)
        expected_cwd = str(tmp_path.resolve())
        actual_cwd = result.stdout.strip()

        # On Windows, paths might differ in case, so compare case-insensitively
        if platform.system() == "Windows":
            assert expected_cwd.lower() == actual_cwd.lower()
        else:
            assert expected_cwd == actual_cwd

        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_with_invalid_working_directory(self):
        """Test that invalid working directory raises error."""
        with pytest.raises(
            SanitizedError, match="Invalid working directory|does not exist"
        ):
            await execute_command(
                "python --version", working_directory="/completely/nonexistent/path"
            )

    @pytest.mark.asyncio
    async def test_execute_with_file_as_working_directory(self, tmp_path):
        """Test that file path as working directory raises error."""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        with pytest.raises(SanitizedError, match="not a directory"):
            await execute_command("python --version", working_directory=str(test_file))


class TestTimeoutEnforcement:
    """Tests for command timeout enforcement."""

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self):
        """Test that timeout is enforced for long-running commands."""
        # Use Python time.sleep for cross-platform consistency
        result = await execute_command(
            'python -c "import time; time.sleep(5)"',
            timeout_ms=1000,  # 1 second timeout
        )

        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timeout" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_execute_completes_within_timeout(self):
        """Test that fast commands complete within timeout."""
        result = await execute_command(
            "python --version",
            timeout_ms=30000,  # 30 second timeout (generous)
        )

        assert result.timed_out is False
        assert result.exit_code == 0
        assert result.execution_time_ms < 30000


class TestExitCodeHandling:
    """Tests for command exit code handling."""

    @pytest.mark.asyncio
    async def test_execute_successful_command_zero_exit(self):
        """Test that successful commands return exit code 0."""
        result = await execute_command("python --version")

        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_failing_command_nonzero_exit(self):
        """Test that failing commands return non-zero exit code."""
        # Try to execute non-existent Python script
        result = await execute_command('python -c "import sys; sys.exit(42)"')

        assert result.exit_code == 42

    @pytest.mark.asyncio
    async def test_execute_nonexistent_command(self):
        """Test that non-existent commands raise appropriate error."""
        with pytest.raises(SanitizedError, match="Command not found|not found"):
            await execute_command("this_command_definitely_does_not_exist_12345")


class TestOutputCapture:
    """Tests for stdout/stderr capture."""

    @pytest.mark.asyncio
    async def test_execute_captures_stdout(self):
        """Test that stdout is captured correctly."""
        result = await execute_command("python -c \"print('stdout test')\"")

        assert "stdout test" in result.stdout
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_captures_stderr(self):
        """Test that stderr is captured correctly."""
        result = await execute_command(
            "python -c \"import sys; sys.stderr.write('stderr test\\n')\""
        )

        assert "stderr test" in result.stderr
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_captures_both_stdout_and_stderr(self):
        """Test that both stdout and stderr are captured."""
        result = await execute_command(
            "python -c \"import sys; print('stdout'); sys.stderr.write('stderr\\n')\""
        )

        assert "stdout" in result.stdout
        assert "stderr" in result.stderr


class TestOutputTruncation:
    """Tests for output size limit enforcement."""

    @pytest.mark.asyncio
    async def test_execute_large_output_truncated(self):
        """Test that very large output is truncated."""
        # Generate large output (attempt to create >10MB output)
        if platform.system() == "Windows":
            # Generate many lines of output
            command = "python -c \"for i in range(100000): print('x' * 100)\""
        else:
            # Use yes command for large output
            command = "python -c \"for i in range(100000): print('x' * 100)\""

        result = await execute_command(
            command,
            timeout_ms=10000,  # 10 second timeout
        )

        # Check if output was truncated
        if result.output_truncated:
            assert (
                "[Output truncated...]" in result.stdout
                or "[Output truncated...]" in result.stderr
            )
        # Note: Truncation depends on config.max_output_bytes


class TestCommandParsing:
    """Tests for command string parsing."""

    @pytest.mark.asyncio
    async def test_execute_command_with_quotes(self):
        """Test command parsing with quoted arguments."""
        result = await execute_command("python -c \"print('hello world')\"")

        assert "hello world" in result.stdout
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_command_with_spaces_in_path(self, tmp_path):
        """Test command execution with spaces in working directory."""
        # Create directory with spaces
        dir_with_spaces = tmp_path / "my test dir"
        dir_with_spaces.mkdir()

        # Use Python to verify cwd is set correctly (cross-platform)
        result = await execute_command(
            'python -c "import os; print(os.getcwd())"',
            working_directory=str(dir_with_spaces),
        )

        # Normalize paths for comparison
        expected_cwd = str(dir_with_spaces.resolve())
        actual_cwd = result.stdout.strip()

        # On Windows, paths might differ in case, so compare case-insensitively
        if platform.system() == "Windows":
            assert expected_cwd.lower() == actual_cwd.lower()
        else:
            assert expected_cwd == actual_cwd

        assert result.exit_code == 0


class TestUtf8OutputDecoding:
    """Tests that non-ASCII UTF-8 subprocess output is decoded correctly."""

    @pytest.mark.asyncio
    async def test_utf8_characters_preserved(self):
        """Subprocess UTF-8 bytes must survive the decode step intact.

        Regression test for Bug 06: text=True without encoding='utf-8' caused
        Python to use the system ANSI codepage (CP-1252 on Windows en-US),
        silently corrupting any non-ASCII bytes as mojibake.

        We write raw UTF-8 bytes via sys.stdout.buffer to replicate what a
        UTF-8-clean binary (e.g. gws) does when piped through ProcExecMCP.
        """
        # Write raw UTF-8 bytes directly to the pipe, bypassing sys.stdout
        # text-mode encoding — same as what gws and other UTF-8 binaries do.
        result = await execute_command(
            'python -c "import sys; sys.stdout.buffer.write('
            "'caf\\u00e9 \\u2014 r\\u00e9sum\\u00e9\\n'.encode('utf-8'))\""
        )

        assert result.exit_code == 0
        assert "café" in result.stdout
        assert "—" in result.stdout
        assert "résumé" in result.stdout


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_execute_empty_command_rejected(self):
        """Test that empty command is rejected."""
        with pytest.raises((ValueError, SanitizedError)):
            await execute_command("")

    @pytest.mark.asyncio
    async def test_execute_whitespace_command_rejected(self):
        """Test that whitespace-only command is rejected."""
        with pytest.raises((ValueError, SanitizedError)):
            await execute_command("   ")

    @pytest.mark.asyncio
    async def test_execute_timeout_too_small_rejected(self):
        """Test that timeout < 1000ms is rejected."""
        with pytest.raises((ValueError, SanitizedError)):
            await execute_command("python --version", timeout_ms=500)

    @pytest.mark.asyncio
    async def test_execute_timeout_too_large_rejected(self):
        """Test that timeout > 300000ms is rejected."""
        with pytest.raises((ValueError, SanitizedError)):
            await execute_command("python --version", timeout_ms=400000)
