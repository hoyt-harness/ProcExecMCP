# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for list_processes tool with mocked psutil."""

import pytest
from unittest.mock import Mock, MagicMock, patch
import psutil

from src.procexec.tools.processes import (
    _get_process_info,
    _filter_processes,
    _sort_processes,
    _limit_processes,
    _validate_process_exists,
    _terminate_process,
    _kill_process_forced,
    list_processes,
    kill_process,
)
from src.procexec.tools.schemas import ProcessInfo, ProcessSortBy
from src.procexec.utils.validation import SanitizedError


class TestGetProcessInfo:
    """Tests for _get_process_info helper function."""

    def test_get_process_info_success(self):
        """Test successful process info retrieval."""
        # Create mock process
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.pid = 1234
        mock_proc.name.return_value = "python.exe"
        mock_proc.status.return_value = "running"
        mock_proc.cpu_percent.return_value = 5.2
        mock_proc.memory_info.return_value = Mock(rss=157286400)  # 150 MB in bytes
        mock_proc.cmdline.return_value = ["python", "script.py"]
        mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
        mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)

        result = _get_process_info(mock_proc)

        assert result is not None
        assert result.pid == 1234
        assert result.name == "python.exe"
        assert result.status == "running"
        assert result.cpu_percent == 5.2
        assert result.memory_mb == 150.0  # 157286400 / (1024*1024) rounded
        assert result.cmdline == "python script.py"

    def test_get_process_info_no_such_process(self):
        """Test handling of NoSuchProcess exception."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.oneshot.side_effect = psutil.NoSuchProcess(1234)

        result = _get_process_info(mock_proc)

        assert result is None

    def test_get_process_info_access_denied(self):
        """Test handling of AccessDenied exception."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.oneshot.side_effect = psutil.AccessDenied(1234)

        result = _get_process_info(mock_proc)

        assert result is None

    def test_get_process_info_zombie_process(self):
        """Test handling of ZombieProcess exception."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.oneshot.side_effect = psutil.ZombieProcess(1234)

        result = _get_process_info(mock_proc)

        assert result is None

    def test_get_process_info_empty_cmdline(self):
        """Test process info when cmdline is empty."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.pid = 1234
        mock_proc.name.return_value = "system"
        mock_proc.status.return_value = "running"
        mock_proc.cpu_percent.return_value = 0.0
        mock_proc.memory_info.return_value = Mock(rss=1048576)  # 1 MB
        mock_proc.cmdline.return_value = []
        mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
        mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)

        result = _get_process_info(mock_proc)

        assert result is not None
        assert result.cmdline == ""

    def test_get_process_info_cmdline_access_denied(self):
        """Test process info when cmdline access is denied."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.pid = 1234
        mock_proc.name.return_value = "protected.exe"
        mock_proc.status.return_value = "running"
        mock_proc.cpu_percent.return_value = 2.0
        mock_proc.memory_info.return_value = Mock(rss=10485760)  # 10 MB
        mock_proc.cmdline.side_effect = psutil.AccessDenied(1234)
        mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
        mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)

        result = _get_process_info(mock_proc)

        assert result is not None
        assert result.cmdline == ""


class TestFilterProcesses:
    """Tests for _filter_processes helper function."""

    def test_filter_processes_no_filter(self):
        """Test filtering with no filter (returns all)."""
        processes = [
            ProcessInfo(
                pid=1,
                name="python.exe",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="chrome.exe",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _filter_processes(processes, None)

        assert len(result) == 2

    def test_filter_processes_case_insensitive(self):
        """Test case-insensitive filtering."""
        processes = [
            ProcessInfo(
                pid=1,
                name="Python.exe",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="CHROME.EXE",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=3,
                name="python3",
                cpu_percent=3.0,
                memory_mb=80.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _filter_processes(processes, "python")

        assert len(result) == 2
        assert all("python" in proc.name.lower() for proc in result)

    def test_filter_processes_substring_match(self):
        """Test substring matching in filter."""
        processes = [
            ProcessInfo(
                pid=1,
                name="python.exe",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="pythonw.exe",
                cpu_percent=2.0,
                memory_mb=50.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=3,
                name="chrome.exe",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _filter_processes(processes, "python")

        assert len(result) == 2

    def test_filter_processes_no_matches(self):
        """Test filtering with no matches."""
        processes = [
            ProcessInfo(
                pid=1,
                name="chrome.exe",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="firefox.exe",
                cpu_percent=8.0,
                memory_mb=150.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _filter_processes(processes, "python")

        assert len(result) == 0


class TestSortProcesses:
    """Tests for _sort_processes helper function."""

    def test_sort_by_cpu_descending(self):
        """Test sorting by CPU (descending)."""
        processes = [
            ProcessInfo(
                pid=1,
                name="a",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="b",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=3,
                name="c",
                cpu_percent=2.0,
                memory_mb=50.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _sort_processes(processes, ProcessSortBy.CPU)

        assert result[0].cpu_percent == 10.0
        assert result[1].cpu_percent == 5.0
        assert result[2].cpu_percent == 2.0

    def test_sort_by_memory_descending(self):
        """Test sorting by memory (descending)."""
        processes = [
            ProcessInfo(
                pid=1,
                name="a",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="b",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=3,
                name="c",
                cpu_percent=2.0,
                memory_mb=50.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _sort_processes(processes, ProcessSortBy.MEMORY)

        assert result[0].memory_mb == 200.0
        assert result[1].memory_mb == 100.0
        assert result[2].memory_mb == 50.0

    def test_sort_by_pid_ascending(self):
        """Test sorting by PID (ascending)."""
        processes = [
            ProcessInfo(
                pid=100,
                name="a",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=10,
                name="b",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=50,
                name="c",
                cpu_percent=2.0,
                memory_mb=50.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _sort_processes(processes, ProcessSortBy.PID)

        assert result[0].pid == 10
        assert result[1].pid == 50
        assert result[2].pid == 100

    def test_sort_by_name_ascending(self):
        """Test sorting by name (ascending, case-insensitive)."""
        processes = [
            ProcessInfo(
                pid=1,
                name="Zebra",
                cpu_percent=5.0,
                memory_mb=100.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=2,
                name="Apple",
                cpu_percent=10.0,
                memory_mb=200.0,
                cmdline="",
                status="running",
            ),
            ProcessInfo(
                pid=3,
                name="banana",
                cpu_percent=2.0,
                memory_mb=50.0,
                cmdline="",
                status="running",
            ),
        ]

        result = _sort_processes(processes, ProcessSortBy.NAME)

        assert result[0].name == "Apple"
        assert result[1].name == "banana"
        assert result[2].name == "Zebra"


class TestLimitProcesses:
    """Tests for _limit_processes helper function."""

    def test_limit_processes_under_limit(self):
        """Test limiting when process count is under limit."""
        processes = [
            ProcessInfo(
                pid=i,
                name=f"proc{i}",
                cpu_percent=1.0,
                memory_mb=10.0,
                cmdline="",
                status="running",
            )
            for i in range(5)
        ]

        result, truncated = _limit_processes(processes, 10)

        assert len(result) == 5
        assert truncated is False

    def test_limit_processes_over_limit(self):
        """Test limiting when process count exceeds limit."""
        processes = [
            ProcessInfo(
                pid=i,
                name=f"proc{i}",
                cpu_percent=1.0,
                memory_mb=10.0,
                cmdline="",
                status="running",
            )
            for i in range(100)
        ]

        result, truncated = _limit_processes(processes, 10)

        assert len(result) == 10
        assert truncated is True

    def test_limit_processes_exact_limit(self):
        """Test limiting when process count equals limit."""
        processes = [
            ProcessInfo(
                pid=i,
                name=f"proc{i}",
                cpu_percent=1.0,
                memory_mb=10.0,
                cmdline="",
                status="running",
            )
            for i in range(10)
        ]

        result, truncated = _limit_processes(processes, 10)

        assert len(result) == 10
        assert truncated is False


class TestListProcessesIntegration:
    """Integration tests for list_processes function with mocked psutil."""

    @pytest.mark.asyncio
    @patch("src.procexec.tools.processes.psutil.process_iter")
    async def test_list_processes_success(self, mock_process_iter):
        """Test successful process listing."""
        # Create mock processes
        mock_procs = []
        for i in range(3):
            mock_proc = Mock(spec=psutil.Process)
            mock_proc.pid = i + 1
            mock_proc.name.return_value = f"proc{i}.exe"
            mock_proc.status.return_value = "running"
            mock_proc.cpu_percent.return_value = float(i * 2)
            mock_proc.memory_info.return_value = Mock(rss=(i + 1) * 10485760)  # MB
            mock_proc.cmdline.return_value = [f"proc{i}"]
            mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
            mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)
            mock_procs.append(mock_proc)

        mock_process_iter.return_value = mock_procs

        result = await list_processes()

        assert result is not None
        assert len(result.processes) == 3
        assert result.total_count == 3
        assert result.truncated is False
        assert result.retrieval_time_ms >= 0  # May be 0 for very fast mocked tests

    @pytest.mark.asyncio
    @patch("src.procexec.tools.processes.psutil.process_iter")
    async def test_list_processes_with_filter(self, mock_process_iter):
        """Test process listing with name filter."""
        # Create mock processes
        mock_procs = []
        names = ["python.exe", "chrome.exe", "python3"]
        for i, name in enumerate(names):
            mock_proc = Mock(spec=psutil.Process)
            mock_proc.pid = i + 1
            mock_proc.name.return_value = name
            mock_proc.status.return_value = "running"
            mock_proc.cpu_percent.return_value = 5.0
            mock_proc.memory_info.return_value = Mock(rss=10485760)
            mock_proc.cmdline.return_value = [name]
            mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
            mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)
            mock_procs.append(mock_proc)

        mock_process_iter.return_value = mock_procs

        result = await list_processes(name_filter="python")

        assert len(result.processes) == 2  # python.exe and python3
        assert all("python" in proc.name.lower() for proc in result.processes)

    @pytest.mark.asyncio
    @patch("src.procexec.tools.processes.psutil.process_iter")
    async def test_list_processes_with_limit(self, mock_process_iter):
        """Test process listing with limit."""
        # Create many mock processes
        mock_procs = []
        for i in range(50):
            mock_proc = Mock(spec=psutil.Process)
            mock_proc.pid = i + 1
            mock_proc.name.return_value = f"proc{i}.exe"
            mock_proc.status.return_value = "running"
            mock_proc.cpu_percent.return_value = 5.0
            mock_proc.memory_info.return_value = Mock(rss=10485760)
            mock_proc.cmdline.return_value = [f"proc{i}"]
            mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
            mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)
            mock_procs.append(mock_proc)

        mock_process_iter.return_value = mock_procs

        result = await list_processes(limit=10)

        assert len(result.processes) == 10
        assert result.total_count == 50
        assert result.truncated is True

    @pytest.mark.asyncio
    @patch("src.procexec.tools.processes.psutil.process_iter")
    async def test_list_processes_handles_exceptions(self, mock_process_iter):
        """Test that exceptions during process iteration are handled."""
        # Create mock processes, some of which raise exceptions
        mock_proc1 = Mock(spec=psutil.Process)
        mock_proc1.oneshot.side_effect = psutil.NoSuchProcess(1)

        mock_proc2 = Mock(spec=psutil.Process)
        mock_proc2.pid = 2
        mock_proc2.name.return_value = "valid.exe"
        mock_proc2.status.return_value = "running"
        mock_proc2.cpu_percent.return_value = 5.0
        mock_proc2.memory_info.return_value = Mock(rss=10485760)
        mock_proc2.cmdline.return_value = ["valid"]
        mock_proc2.oneshot.return_value.__enter__ = Mock(return_value=None)
        mock_proc2.oneshot.return_value.__exit__ = Mock(return_value=None)

        mock_process_iter.return_value = [mock_proc1, mock_proc2]

        result = await list_processes()

        # Should skip the failed process and return the valid one
        assert len(result.processes) == 1
        assert result.processes[0].name == "valid.exe"

    @pytest.mark.asyncio
    @patch("src.procexec.tools.processes.psutil.process_iter")
    async def test_list_processes_sort_by_memory(self, mock_process_iter):
        """Test sorting by memory."""
        # Create mock processes with different memory usage
        mock_procs = []
        memory_sizes = [50, 200, 100]  # MB
        for i, mem_mb in enumerate(memory_sizes):
            mock_proc = Mock(spec=psutil.Process)
            mock_proc.pid = i + 1
            mock_proc.name.return_value = f"proc{i}.exe"
            mock_proc.status.return_value = "running"
            mock_proc.cpu_percent.return_value = 5.0
            mock_proc.memory_info.return_value = Mock(rss=mem_mb * 1024 * 1024)
            mock_proc.cmdline.return_value = [f"proc{i}"]
            mock_proc.oneshot.return_value.__enter__ = Mock(return_value=None)
            mock_proc.oneshot.return_value.__exit__ = Mock(return_value=None)
            mock_procs.append(mock_proc)

        mock_process_iter.return_value = mock_procs

        result = await list_processes(sort_by=ProcessSortBy.MEMORY)

        # Should be sorted by memory descending: 200, 100, 50
        assert result.processes[0].memory_mb == 200.0
        assert result.processes[1].memory_mb == 100.0
        assert result.processes[2].memory_mb == 50.0


class TestInputValidation:
    """Tests for input validation via Pydantic."""

    @pytest.mark.asyncio
    async def test_invalid_limit_too_small(self):
        """Test that limit < 1 is rejected."""
        with pytest.raises(ValueError):
            await list_processes(limit=0)

    @pytest.mark.asyncio
    async def test_invalid_limit_too_large(self):
        """Test that limit > 1000 is rejected."""
        with pytest.raises(ValueError):
            await list_processes(limit=2000)


# Phase 6: kill_process unit tests


class TestValidateProcessExists:
    """Tests for _validate_process_exists helper function."""

    @patch("src.procexec.tools.processes.psutil.pid_exists")
    def test_process_exists(self, mock_pid_exists):
        """Test checking for existing process."""
        mock_pid_exists.return_value = True

        result = _validate_process_exists(1234)

        assert result is True
        mock_pid_exists.assert_called_once_with(1234)

    @patch("src.procexec.tools.processes.psutil.pid_exists")
    def test_process_does_not_exist(self, mock_pid_exists):
        """Test checking for non-existent process."""
        mock_pid_exists.return_value = False

        result = _validate_process_exists(999999)

        assert result is False
        mock_pid_exists.assert_called_once_with(999999)


class TestTerminateProcess:
    """Tests for _terminate_process helper function."""

    def test_graceful_termination_success(self):
        """Test successful graceful termination."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.terminate = Mock()
        mock_proc.wait = Mock()  # Process exits normally

        success, message = _terminate_process(mock_proc, timeout_seconds=5.0)

        assert success is True
        assert "gracefully" in message.lower()
        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=5.0)

    def test_termination_timeout(self):
        """Test termination timeout."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.terminate = Mock()
        mock_proc.wait = Mock(side_effect=psutil.TimeoutExpired(1234, 5.0))

        success, message = _terminate_process(mock_proc, timeout_seconds=5.0)

        assert success is False
        assert "timeout" in message.lower()
        mock_proc.terminate.assert_called_once()

    def test_process_already_gone(self):
        """Test terminating already-terminated process."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.terminate = Mock(side_effect=psutil.NoSuchProcess(1234))

        success, message = _terminate_process(mock_proc, timeout_seconds=5.0)

        assert success is True
        assert "already terminated" in message.lower()

    def test_access_denied(self):
        """Test termination with access denied."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.terminate = Mock(side_effect=psutil.AccessDenied(1234))

        success, message = _terminate_process(mock_proc, timeout_seconds=5.0)

        assert success is False
        assert "access denied" in message.lower()


class TestKillProcessForced:
    """Tests for _kill_process_forced helper function."""

    @patch("src.procexec.tools.processes.psutil.pid_exists")
    def test_forced_kill_success(self, mock_pid_exists):
        """Test successful forced kill."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.pid = 1234
        mock_proc.kill = Mock()
        mock_proc.wait = Mock()
        mock_pid_exists.return_value = False  # Process is gone

        success, message = _kill_process_forced(mock_proc)

        assert success is True
        assert "killed forcefully" in message.lower()
        mock_proc.kill.assert_called_once()

    @patch("src.procexec.tools.processes.psutil.pid_exists")
    def test_forced_kill_still_alive(self, mock_pid_exists):
        """Test forced kill when process survives."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.pid = 1234
        mock_proc.kill = Mock()
        mock_proc.wait = Mock()
        mock_pid_exists.return_value = True  # Process still exists

        success, message = _kill_process_forced(mock_proc)

        assert success is False
        assert "still exists" in message.lower()

    def test_process_already_gone_kill(self):
        """Test forced kill on already-terminated process."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.kill = Mock(side_effect=psutil.NoSuchProcess(1234))

        success, message = _kill_process_forced(mock_proc)

        assert success is True
        assert "already terminated" in message.lower()

    def test_access_denied_kill(self):
        """Test forced kill with access denied."""
        mock_proc = Mock(spec=psutil.Process)
        mock_proc.kill = Mock(side_effect=psutil.AccessDenied(1234))

        success, message = _kill_process_forced(mock_proc)

        assert success is False
        assert "access denied" in message.lower()


class TestKillProcessIntegration:
    """Integration tests for kill_process function with mocked psutil."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "false"})
    async def test_kill_process_disabled(self):
        """Test that kill_process is disabled by default."""
        with pytest.raises(SanitizedError, match="Process termination is disabled"):
            await kill_process(pid=1234)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    async def test_kill_nonexistent_process(self, mock_validate):
        """Test attempting to kill non-existent process."""
        mock_validate.return_value = False

        result = await kill_process(pid=999999)

        assert result.success is False
        assert result.pid == 999999
        assert "does not exist" in result.message.lower()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    @patch("src.procexec.tools.processes.psutil.Process")
    @patch("src.procexec.tools.processes._terminate_process")
    async def test_kill_process_graceful_success(
        self, mock_terminate, mock_process_class, mock_validate
    ):
        """Test successful graceful process termination."""
        mock_validate.return_value = True
        mock_proc = MagicMock()
        mock_process_class.return_value = mock_proc
        mock_terminate.return_value = (True, "Process terminated gracefully")

        result = await kill_process(pid=1234, force=False, timeout_seconds=5.0)

        assert result.success is True
        assert result.pid == 1234
        assert result.forced is False
        assert result.termination_time_ms >= 0
        mock_terminate.assert_called_once_with(mock_proc, 5.0)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    @patch("src.procexec.tools.processes.psutil.Process")
    @patch("src.procexec.tools.processes._kill_process_forced")
    async def test_kill_process_forced_success(
        self, mock_kill_forced, mock_process_class, mock_validate
    ):
        """Test successful forced process kill."""
        mock_validate.return_value = True
        mock_proc = MagicMock()
        mock_process_class.return_value = mock_proc
        mock_kill_forced.return_value = (True, "Process killed forcefully")

        result = await kill_process(pid=1234, force=True)

        assert result.success is True
        assert result.pid == 1234
        assert result.forced is True
        assert result.termination_time_ms >= 0
        mock_kill_forced.assert_called_once_with(mock_proc)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    @patch("src.procexec.tools.processes.psutil.Process")
    async def test_kill_process_access_denied(self, mock_process_class, mock_validate):
        """Test kill process with access denied."""
        mock_validate.return_value = True
        mock_process_class.side_effect = psutil.AccessDenied(1234)

        result = await kill_process(pid=1234)

        assert result.success is False
        assert result.pid == 1234
        assert "access denied" in result.message.lower()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    @patch("src.procexec.tools.processes.psutil.Process")
    async def test_kill_process_disappeared_during_operation(
        self, mock_process_class, mock_validate
    ):
        """Test process disappearing during kill operation."""
        mock_validate.return_value = True
        mock_process_class.side_effect = psutil.NoSuchProcess(1234)

        result = await kill_process(pid=1234)

        assert result.success is True
        assert result.pid == 1234
        assert "no longer exists" in result.message.lower()

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    @patch("src.procexec.tools.processes._validate_process_exists")
    @patch("src.procexec.tools.processes.psutil.Process")
    @patch("src.procexec.tools.processes._terminate_process")
    async def test_kill_process_graceful_failure(
        self, mock_terminate, mock_process_class, mock_validate
    ):
        """Test graceful termination that fails (timeout)."""
        mock_validate.return_value = True
        mock_proc = MagicMock()
        mock_process_class.return_value = mock_proc
        mock_terminate.return_value = (
            False,
            "Process did not terminate within 5.0s timeout",
        )

        result = await kill_process(pid=1234, force=False, timeout_seconds=5.0)

        assert result.success is False
        assert result.pid == 1234
        assert result.forced is False
        assert "timeout" in result.message.lower()


class TestKillProcessInputValidation:
    """Tests for kill_process input validation."""

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    async def test_invalid_pid_zero(self):
        """Test that PID 0 is rejected."""
        with pytest.raises(ValueError):
            await kill_process(pid=0)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    async def test_invalid_pid_negative(self):
        """Test that negative PID is rejected."""
        with pytest.raises(ValueError):
            await kill_process(pid=-1)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    async def test_invalid_timeout_too_small(self):
        """Test that timeout < 0.1 is rejected."""
        with pytest.raises(ValueError):
            await kill_process(pid=1234, timeout_seconds=0.05)

    @pytest.mark.asyncio
    @patch.dict("os.environ", {"PROCEXEC_ENABLE_KILL": "true"})
    async def test_invalid_timeout_too_large(self):
        """Test that timeout > 30 is rejected."""
        with pytest.raises(ValueError):
            await kill_process(pid=1234, timeout_seconds=60.0)
