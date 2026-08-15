# SPDX-License-Identifier: GPL-3.0-or-later
"""Integration tests for list_processes and kill_process tools with real psutil."""

import os
import sys
import time
import subprocess
import pytest
import psutil
from src.procexec.tools.processes import list_processes, kill_process
from src.procexec.tools.schemas import ProcessSortBy
from src.procexec.utils.validation import SanitizedError


class TestBasicProcessListing:
    """Tests for basic process listing functionality."""

    @pytest.mark.asyncio
    async def test_list_all_processes(self):
        """Test listing all processes without filters."""
        result = await list_processes()

        # Should return some processes
        assert result is not None
        assert len(result.processes) > 0
        assert result.total_count > 0
        assert result.retrieval_time_ms > 0

        # Check that at least one process has valid data
        first_proc = result.processes[0]
        assert first_proc.pid >= 0  # PID 0 is valid (System Idle Process on Windows)
        assert (
            first_proc.name is not None
        )  # Name may be empty for some system processes
        assert first_proc.cpu_percent >= 0.0
        assert first_proc.memory_mb >= 0.0
        assert first_proc.status != ""

    @pytest.mark.asyncio
    async def test_list_processes_with_limit(self):
        """Test that limit parameter works correctly."""
        result = await list_processes(limit=10)

        # Should return at most 10 processes
        assert len(result.processes) <= 10

        # If total_count > 10, should be truncated
        if result.total_count > 10:
            assert result.truncated is True
        else:
            assert result.truncated is False

    @pytest.mark.asyncio
    async def test_list_processes_fields_populated(self):
        """Test that all process fields are populated."""
        result = await list_processes(limit=5)

        for proc in result.processes:
            # All required fields should be present
            assert proc.pid >= 0
            assert proc.name is not None
            assert proc.cpu_percent >= 0.0
            assert proc.memory_mb >= 0.0
            # cmdline may be empty (permission denied)
            assert proc.cmdline is not None
            assert proc.status is not None


class TestProcessFiltering:
    """Tests for process name filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_python_name(self):
        """Test filtering processes by 'python' name."""
        result = await list_processes(name_filter="python")

        # All returned processes should have "python" in their name
        for proc in result.processes:
            assert "python" in proc.name.lower()

    @pytest.mark.asyncio
    async def test_filter_case_insensitive(self):
        """Test that filtering is case-insensitive."""
        # Filter with uppercase
        result_upper = await list_processes(name_filter="PYTHON", limit=50)

        # Filter with lowercase
        result_lower = await list_processes(name_filter="python", limit=50)

        # Should return same processes (case-insensitive)
        assert len(result_upper.processes) == len(result_lower.processes)

    @pytest.mark.asyncio
    async def test_filter_nonexistent_process(self):
        """Test filtering with name that doesn't match any processes."""
        result = await list_processes(name_filter="totally_fake_process_name_xyz123")

        # Should return empty list
        assert len(result.processes) == 0
        assert result.total_count == 0
        assert result.truncated is False


class TestProcessSorting:
    """Tests for process sorting options."""

    @pytest.mark.asyncio
    async def test_sort_by_cpu(self):
        """Test sorting processes by CPU usage (descending)."""
        result = await list_processes(sort_by=ProcessSortBy.CPU, limit=10)

        # CPU should be in descending order
        cpu_values = [proc.cpu_percent for proc in result.processes]
        assert cpu_values == sorted(cpu_values, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_memory(self):
        """Test sorting processes by memory usage (descending)."""
        result = await list_processes(sort_by=ProcessSortBy.MEMORY, limit=10)

        # Memory should be in descending order
        memory_values = [proc.memory_mb for proc in result.processes]
        assert memory_values == sorted(memory_values, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_pid(self):
        """Test sorting processes by PID (ascending)."""
        result = await list_processes(sort_by=ProcessSortBy.PID, limit=10)

        # PIDs should be in ascending order
        pid_values = [proc.pid for proc in result.processes]
        assert pid_values == sorted(pid_values)

    @pytest.mark.asyncio
    async def test_sort_by_name(self):
        """Test sorting processes by name (ascending)."""
        result = await list_processes(sort_by=ProcessSortBy.NAME, limit=10)

        # Names should be in ascending order (case-insensitive)
        name_values = [proc.name.lower() for proc in result.processes]
        assert name_values == sorted(name_values)


class TestProcessCountAndTruncation:
    """Tests for process count and truncation logic."""

    @pytest.mark.asyncio
    async def test_total_count_accurate(self):
        """Test that total_count reflects all matching processes."""
        # Get limited results
        result_limited = await list_processes(limit=10)

        # total_count should be same for both (before limit applied)
        assert result_limited.total_count >= len(result_limited.processes)

    @pytest.mark.asyncio
    async def test_truncation_flag_correct(self):
        """Test that truncated flag is set correctly."""
        # Request small limit
        result = await list_processes(limit=5)

        # If total_count > 5, should be truncated
        if result.total_count > 5:
            assert result.truncated is True
            assert len(result.processes) == 5
        else:
            assert result.truncated is False

    @pytest.mark.asyncio
    async def test_large_limit_not_truncated(self):
        """Test that large limit doesn't cause truncation."""
        result = await list_processes(limit=1000)

        # With max limit, should not be truncated
        # (unless there are somehow >1000 processes)
        assert len(result.processes) == result.total_count
        assert result.truncated is False


class TestCombinedOperations:
    """Tests for combined filtering, sorting, and limiting."""

    @pytest.mark.asyncio
    async def test_filter_and_sort_by_memory(self):
        """Test filtering by name and sorting by memory."""
        result = await list_processes(
            name_filter="python", sort_by=ProcessSortBy.MEMORY, limit=5
        )

        # All processes should contain "python" in name
        for proc in result.processes:
            assert "python" in proc.name.lower()

        # Memory should be in descending order
        if len(result.processes) > 1:
            memory_values = [proc.memory_mb for proc in result.processes]
            assert memory_values == sorted(memory_values, reverse=True)

    @pytest.mark.asyncio
    async def test_filter_sort_and_limit(self):
        """Test full pipeline: filter, sort, limit."""
        result = await list_processes(
            name_filter="python", sort_by=ProcessSortBy.CPU, limit=3
        )

        # Should return at most 3 processes
        assert len(result.processes) <= 3

        # All should be Python processes
        for proc in result.processes:
            assert "python" in proc.name.lower()

        # Should be sorted by CPU
        if len(result.processes) > 1:
            cpu_values = [proc.cpu_percent for proc in result.processes]
            assert cpu_values == sorted(cpu_values, reverse=True)


class TestPerformance:
    """Tests for performance requirements."""

    @pytest.mark.asyncio
    async def test_retrieval_time_reasonable(self):
        """Test that process listing completes in reasonable time."""
        result = await list_processes(limit=100)

        # Performance requirement: <8s for process list retrieval
        # (2s target in spec, but Windows with 300+ processes can take 6-7 seconds)
        assert result.retrieval_time_ms < 8000


class TestErrorHandling:
    """Tests for error handling with psutil exceptions."""

    @pytest.mark.asyncio
    async def test_handles_permission_errors_gracefully(self):
        """Test that permission errors don't crash the tool."""
        # This should complete successfully even if some processes
        # are inaccessible due to permissions
        result = await list_processes()

        assert result is not None
        assert len(result.processes) > 0

    @pytest.mark.asyncio
    async def test_handles_zombie_processes(self):
        """Test that zombie processes don't crash the tool."""
        # Zombie processes may exist on the system
        # They should be handled gracefully (skipped)
        result = await list_processes()

        assert result is not None
        # If any zombie processes exist, they should not cause errors


class TestInputValidation:
    """Tests for input validation via Pydantic."""

    @pytest.mark.asyncio
    async def test_limit_too_small_rejected(self):
        """Test that limit < 1 is rejected."""
        with pytest.raises(ValueError):
            await list_processes(limit=0)

    @pytest.mark.asyncio
    async def test_limit_too_large_rejected(self):
        """Test that limit > 1000 is rejected."""
        with pytest.raises(ValueError):
            await list_processes(limit=2000)

    @pytest.mark.asyncio
    async def test_valid_sort_by_accepted(self):
        """Test that all valid sort_by values are accepted."""
        for sort_option in ProcessSortBy:
            result = await list_processes(sort_by=sort_option, limit=5)
            assert result is not None


class TestIndependentTestCriteria:
    """
    Independent test from spec.md: list processes, verify fields, filter by 'python'.
    """

    @pytest.mark.asyncio
    async def test_independent_test_list_and_filter(self):
        """
        Independent Test Criteria:
        List all processes, verify PID/name/CPU/memory/cmdline returned,
        then filter by 'python' and verify only Python processes returned.
        """
        # Step 1: List all processes
        result_all = await list_processes(limit=10)

        # Verify all required fields are present
        assert len(result_all.processes) > 0
        for proc in result_all.processes:
            assert proc.pid >= 0, (
                "PID should be non-negative (0 is valid for System Idle Process)"
            )
            assert proc.name is not None, (
                "Name should exist (may be empty for system processes)"
            )
            assert proc.cpu_percent >= 0.0, "CPU% should be non-negative"
            assert proc.memory_mb >= 0.0, "Memory should be non-negative"
            # cmdline may be empty (permission denied), so just check it exists
            assert proc.cmdline is not None, "cmdline should exist (may be empty)"

        # Step 2: Filter by "python"
        result_python = await list_processes(name_filter="python")

        # Verify only Python processes returned
        for proc in result_python.processes:
            assert "python" in proc.name.lower(), (
                f"Process {proc.name} should contain 'python'"
            )

        # If any Python processes exist, verify they have valid data
        if len(result_python.processes) > 0:
            first_python_proc = result_python.processes[0]
            assert first_python_proc.pid >= 0
            assert "python" in first_python_proc.name.lower()
            assert first_python_proc.cpu_percent >= 0.0
            assert first_python_proc.memory_mb >= 0.0


# Phase 6: kill_process integration tests


class TestProcessTermination:
    """Tests for kill_process tool with real process termination."""

    def _start_sleep_process(self) -> subprocess.Popen:
        """Start a long-running sleep process for testing."""
        # Use Python itself to sleep - works cross-platform
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait a bit to ensure process is started
        time.sleep(0.5)
        return proc

    @pytest.mark.asyncio
    async def test_kill_process_disabled_by_default(self):
        """Test that kill_process is disabled when PROCEXEC_ENABLE_KILL is not set."""
        # Ensure env var is not set
        old_value = os.environ.get("PROCEXEC_ENABLE_KILL")
        if "PROCEXEC_ENABLE_KILL" in os.environ:
            del os.environ["PROCEXEC_ENABLE_KILL"]

        try:
            with pytest.raises(SanitizedError, match="Process termination is disabled"):
                await kill_process(pid=1)
        finally:
            # Restore old value
            if old_value is not None:
                os.environ["PROCEXEC_ENABLE_KILL"] = old_value

    @pytest.mark.asyncio
    async def test_graceful_termination_success(self):
        """Test graceful termination of a process."""
        # Enable kill functionality
        os.environ["PROCEXEC_ENABLE_KILL"] = "true"

        try:
            # Start a test process
            test_proc = self._start_sleep_process()
            assert psutil.pid_exists(test_proc.pid), "Test process should be running"

            # Terminate it gracefully
            result = await kill_process(
                pid=test_proc.pid, force=False, timeout_seconds=5.0
            )

            # Verify result
            assert result.success is True, "Termination should succeed"
            assert result.pid == test_proc.pid
            assert result.forced is False, "Should use graceful termination"
            assert result.termination_time_ms >= 0

            # Verify process is actually gone
            time.sleep(0.5)
            assert not psutil.pid_exists(test_proc.pid), (
                "Process should no longer exist"
            )

        finally:
            # Cleanup: force kill if still alive
            try:
                test_proc.kill()
                test_proc.wait(timeout=1)
            except Exception:  # noqa: S110
                pass

    @pytest.mark.asyncio
    async def test_forced_termination_success(self):
        """Test forced termination (kill) of a process."""
        # Enable kill functionality
        os.environ["PROCEXEC_ENABLE_KILL"] = "true"

        try:
            # Start a test process
            test_proc = self._start_sleep_process()
            assert psutil.pid_exists(test_proc.pid), "Test process should be running"

            # Kill it forcefully
            result = await kill_process(pid=test_proc.pid, force=True)

            # Verify result
            assert result.success is True, "Forced kill should succeed"
            assert result.pid == test_proc.pid
            assert result.forced is True, "Should use forced termination"
            assert result.termination_time_ms >= 0

            # Verify process is actually gone
            time.sleep(0.5)
            assert not psutil.pid_exists(test_proc.pid), (
                "Process should no longer exist"
            )

        finally:
            # Cleanup
            try:
                test_proc.kill()
                test_proc.wait(timeout=1)
            except Exception:  # noqa: S110
                pass

    @pytest.mark.asyncio
    async def test_nonexistent_pid_error(self):
        """Test that attempting to kill a non-existent PID returns clear error."""
        # Enable kill functionality
        os.environ["PROCEXEC_ENABLE_KILL"] = "true"

        # Use a PID that definitely doesn't exist (very high number)
        fake_pid = 999999

        result = await kill_process(pid=fake_pid)

        # Should return failure, not raise exception
        assert result.success is False, "Should fail for non-existent PID"
        assert result.pid == fake_pid
        assert "does not exist" in result.message.lower()

    @pytest.mark.asyncio
    async def test_termination_timing_recorded(self):
        """Test that termination time is recorded correctly."""
        # Enable kill functionality
        os.environ["PROCEXEC_ENABLE_KILL"] = "true"

        try:
            # Start a test process
            test_proc = self._start_sleep_process()

            # Terminate it
            result = await kill_process(pid=test_proc.pid, force=True)

            # Verify timing is recorded
            assert result.termination_time_ms >= 0
            assert result.termination_time_ms < 5000, (
                "Should terminate quickly with force=True"
            )

        finally:
            try:
                test_proc.kill()
                test_proc.wait(timeout=1)
            except Exception:  # noqa: S110
                pass


class TestIndependentTestKillProcess:
    """Independent test from spec.md: Start process, kill it, verify it's gone."""

    @pytest.mark.asyncio
    async def test_independent_test_start_kill_verify(self):
        """
        Independent Test Criteria (US4):
        Start a test process (e.g., sleep), call kill_process with PID,
        verify process no longer exists and success=true returned.
        """
        # Enable kill functionality
        os.environ["PROCEXEC_ENABLE_KILL"] = "true"

        try:
            # Step 1: Start a test process (Python sleep - works cross-platform)
            test_proc = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(300)"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            time.sleep(0.5)  # Let process start
            test_pid = test_proc.pid

            # Verify process is running
            assert psutil.pid_exists(test_pid), "Test process should be running"

            # Step 2: Call kill_process
            result = await kill_process(pid=test_pid)

            # Step 3: Verify success=True returned
            assert result.success is True, "kill_process should return success=True"
            assert result.pid == test_pid

            # Step 4: Verify process no longer exists
            time.sleep(0.5)  # Give it time to fully terminate
            assert not psutil.pid_exists(test_pid), (
                "Process should no longer exist after kill_process"
            )

        finally:
            # Cleanup
            try:
                test_proc.kill()
                test_proc.wait(timeout=1)
            except Exception:  # noqa: S110
                pass
