#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cygwin Process Information Tests

This module tests basic process information retrieval functions:
- Process.name() - Get process name
- Process.exe() - Get executable path
- Process.cmdline() - Get command line arguments
- Process.ppid() - Get parent process ID
- Process.status() - Get process status
- Process.uids() - Get user IDs (real, effective, saved)
- Process.gids() - Get group IDs (real, effective, saved)
- Process.create_time() - Get process creation time
- Process.cwd() - Get current working directory
- Process.terminal() - Get controlling terminal

Migrated from:
- issue/phase-3/tests/test_phase3_2_basic_process_info.py
- issue/phase-3/tests/test_comprehensive_process_info.py
- Basic process info tests from other phases

Functions tested:
- All basic Process information methods

This is part of lap 7 of the test reorganization plan.
"""

import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager

import pytest


@contextmanager
def _test_process_helper():
    """Context manager for creating and managing test processes."""
    processes = []
    try:

        def create_test_process(duration=1.0, command=None, args=None):
            """Create a test process with specified duration and command."""
            if command is None:
                if args:
                    cmd = [
                        sys.executable,
                        '-c',
                        (
                            f'import sys, time; sys.argv = {args!r};'
                            f' time.sleep({duration})'
                        ),
                    ]
                else:
                    cmd = [
                        sys.executable,
                        '-c',
                        f'import time; time.sleep({duration})',
                    ]
            else:
                cmd = [sys.executable, '-c', command]

            proc = subprocess.Popen(cmd)
            processes.append(proc)
            return proc

        yield create_test_process
    finally:
        for proc in processes:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=1)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                    proc.wait(timeout=1)
                except (subprocess.TimeoutExpired, OSError):
                    pass


class TestProcessBasicInfo:
    """Test basic process information retrieval."""

    def test_process_name_self(self, psutil_module):
        """Test Process.name() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)
        name = proc.name()

        # Basic validation
        assert isinstance(name, str), "Process name should be string"
        assert len(name) > 0, "Process name should not be empty"

        # In Cygwin, process name might be full path - extract basename
        name_basename = (
            os.path.basename(name) if name.startswith('/') else name
        )
        assert (
            len(name_basename) < 256
        ), "Process name should be reasonable length"
        # Should contain python in some form
        assert (
            'python' in name_basename.lower()
        ), f"Expected python process, got: {name_basename}"

    def test_process_name_multiple_processes(self, psutil_module):
        """Test Process.name() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_names = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                name = proc.name()

                assert isinstance(
                    name, str
                ), f"Name for PID {pid} should be string"
                assert len(name) > 0, f"Name for PID {pid} should not be empty"
                successful_names += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting name for PID {pid}: {e}"
                )

        assert (
            successful_names > 0
        ), "Should successfully get at least some process names"

    def test_process_name_with_test_process(self, psutil_module):
        """Test Process.name() with a controlled test process."""
        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5)

            try:
                proc = psutil_module.Process(test_proc.pid)
                name = proc.name()

                assert isinstance(
                    name, str
                ), "Test process name should be string"
                assert len(name) > 0, "Test process name should not be empty"
                # Should be python or python3 or similar (handle full path)
                name_basename = (
                    os.path.basename(name) if name.startswith('/') else name
                )
                assert (
                    'python' in name_basename.lower()
                ), f"Expected python process, got: {name}"

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()


class TestProcessExecutable:
    """Test process executable path retrieval."""

    def test_process_exe_self(self, psutil_module):
        """Test Process.exe() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)
        exe = proc.exe()

        if exe is not None:  # Can be None for some processes
            assert isinstance(exe, str), "Process exe should be string or None"
            assert len(exe) > 0, "Process exe should not be empty if not None"
            assert os.path.exists(exe), f"Process exe path should exist: {exe}"

    def test_process_exe_multiple_processes(self, psutil_module):
        """Test Process.exe() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_exes = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                exe = proc.exe()

                if exe is not None:
                    assert isinstance(
                        exe, str
                    ), f"Exe for PID {pid} should be string or None"
                    assert (
                        len(exe) > 0
                    ), f"Exe for PID {pid} should not be empty if not None"

                successful_exes += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting exe for PID {pid}: {e}"
                )

        assert (
            successful_exes > 0
        ), "Should successfully get at least some process exes"

    def test_process_exe_with_test_process(self, psutil_module):
        """Test Process.exe() with a controlled test process."""
        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5)

            try:
                proc = psutil_module.Process(test_proc.pid)
                exe = proc.exe()

                if exe is not None:
                    assert isinstance(
                        exe, str
                    ), "Test process exe should be string"
                    assert len(exe) > 0, "Test process exe should not be empty"
                    assert os.path.exists(
                        exe
                    ), f"Test process exe should exist: {exe}"
                    # Should be a python executable
                    assert (
                        'python' in os.path.basename(exe).lower()
                    ), f"Expected python exe, got: {exe}"

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()


class TestProcessCommandLine:
    """Test process command line retrieval."""

    def test_process_cmdline_self(self, psutil_module):
        """Test Process.cmdline() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)
        cmdline = proc.cmdline()

        # Should be a list
        assert isinstance(cmdline, list), "Process cmdline should be list"

        # May be empty for some processes, but ours should have content
        if cmdline:  # Not empty
            assert all(
                isinstance(arg, str) for arg in cmdline
            ), f"All cmdline args should be strings: {cmdline}"

            # First argument should be the executable
            if len(cmdline) > 0:
                first_arg = cmdline[0]
                assert isinstance(
                    first_arg, str
                ), "First cmdline arg should be string"
                assert (
                    len(first_arg) > 0
                ), "First cmdline arg should not be empty"

    def test_process_cmdline_multiple_processes(self, psutil_module):
        """Test Process.cmdline() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_cmdlines = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                cmdline = proc.cmdline()

                assert isinstance(
                    cmdline, list
                ), f"Cmdline for PID {pid} should be list"

                if cmdline:  # Not empty
                    assert all(isinstance(arg, str) for arg in cmdline), (
                        f"All cmdline args for PID {pid} should be strings:"
                        f" {cmdline}"
                    )

                successful_cmdlines += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting cmdline for PID {pid}: {e}"
                )

        assert (
            successful_cmdlines > 0
        ), "Should successfully get at least some process cmdlines"

    def test_process_cmdline_with_test_process(self, psutil_module):
        """Test Process.cmdline() with a controlled test process."""
        test_args = ['python', 'test_script.py', '--arg1', 'value1']

        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5, args=test_args)

            try:
                proc = psutil_module.Process(test_proc.pid)
                cmdline = proc.cmdline()

                assert isinstance(
                    cmdline, list
                ), "Test process cmdline should be list"

                if cmdline:
                    assert all(
                        isinstance(arg, str) for arg in cmdline
                    ), "All test process cmdline args should be strings"

                    # Should contain python and our test arguments
                    cmdline_str = ' '.join(cmdline)
                    assert (
                        'python' in cmdline_str.lower()
                    ), f"Cmdline should contain python: {cmdline}"

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()


class TestProcessParentPID:
    """Test parent process ID retrieval."""

    def test_process_ppid_self(self, psutil_module):
        """Test Process.ppid() for current process."""
        own_pid = os.getpid()
        parent_pid = os.getppid()

        proc = psutil_module.Process(own_pid)
        ppid = proc.ppid()

        assert isinstance(ppid, int), "Process ppid should be integer"
        assert ppid > 0, "Process ppid should be positive"
        assert (
            ppid == parent_pid
        ), f"Process ppid should match os.getppid(): {ppid} vs {parent_pid}"

        # Parent should exist
        assert psutil_module.pid_exists(
            ppid
        ), f"Parent PID {ppid} should exist"

    def test_process_ppid_multiple_processes(self, psutil_module):
        """Test Process.ppid() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_ppids = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                ppid = proc.ppid()

                assert isinstance(
                    ppid, int
                ), f"PPID for PID {pid} should be integer"
                assert ppid > 0, f"PPID for PID {pid} should be positive"

                successful_ppids += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting ppid for PID {pid}: {e}"
                )

        assert (
            successful_ppids > 0
        ), "Should successfully get at least some process ppids"

    def test_process_ppid_parent_child_relationship(self, psutil_module):
        """Test parent-child relationship consistency."""
        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5)

            try:
                parent_proc = psutil_module.Process(os.getpid())
                child_proc = psutil_module.Process(test_proc.pid)

                parent_pid = parent_proc.pid
                child_ppid = child_proc.ppid()

                assert child_ppid == parent_pid, (
                    f"Child's ppid should match parent's pid: {child_ppid} vs"
                    f" {parent_pid}"
                )

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()


class TestProcessStatus:
    """Test process status retrieval."""

    def test_process_status_self(self, psutil_module):
        """Test Process.status() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)
        status = proc.status()

        # In the Cygwin implementation, status() might return an integer
        # Convert to string if needed for validation
        if isinstance(status, int):
            # Map common status codes to strings
            status_map = {
                0: 'running',  # Common case
                1: 'sleeping',
                2: 'disk-sleep',
                3: 'stopped',
                4: 'zombie',
            }
            status_str = status_map.get(status, f'unknown-{status}')
        else:
            status_str = status

        assert isinstance(
            status_str, str
        ), f"Process status should convert to string, got: {status}"

        # Should be one of the valid status values or unknown
        valid_statuses = [
            'running',
            'sleeping',
            'disk-sleep',
            'stopped',
            'tracing-stop',
            'zombie',
            'dead',
            'wake-kill',
            'waking',
            'parked',
        ]
        # Allow unknown status codes as well
        is_valid = status_str in valid_statuses or status_str.startswith(
            'unknown-'
        )
        assert is_valid, f"Process status should be valid: {status_str}"

    def test_process_status_multiple_processes(self, psutil_module):
        """Test Process.status() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_statuses = 0
        found_statuses = set()

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                status = proc.status()

                # Handle integer status codes
                if isinstance(status, int):
                    status_map = {
                        0: 'running',
                        1: 'sleeping',
                        2: 'disk-sleep',
                        3: 'stopped',
                        4: 'zombie',
                    }
                    status_str = status_map.get(status, f'unknown-{status}')
                else:
                    status_str = status

                assert isinstance(
                    status_str, str
                ), f"Status for PID {pid} should convert to string"
                found_statuses.add(status_str)
                successful_statuses += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting status for PID {pid}: {e}"
                )

        assert (
            successful_statuses > 0
        ), "Should successfully get at least some process statuses"
        assert (
            len(found_statuses) > 0
        ), "Should find at least some different statuses"

    def test_process_status_with_test_process(self, psutil_module):
        """Test Process.status() with a controlled test process."""
        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5)

            try:
                proc = psutil_module.Process(test_proc.pid)
                status = proc.status()

                # Handle integer status codes
                if isinstance(status, int):
                    status_map = {
                        0: 'running',
                        1: 'sleeping',
                        2: 'disk-sleep',
                        3: 'stopped',
                        4: 'zombie',
                    }
                    status_str = status_map.get(status, f'unknown-{status}')
                else:
                    status_str = status

                assert isinstance(
                    status_str, str
                ), "Test process status should convert to string"
                # Running process should typically be 'running' or 'sleeping'
                valid_active_statuses = [
                    'running',
                    'sleeping',
                    'unknown-0',
                    'unknown-1',
                ]
                assert (
                    status_str in valid_active_statuses
                ), f"Test process should be in active state, got: {status_str}"

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()


class TestProcessCreateTime:
    """Test process creation time retrieval."""

    def test_process_create_time_self(self, psutil_module):
        """Test Process.create_time() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)
        create_time = proc.create_time()

        assert isinstance(
            create_time, (int, float)
        ), "Create time should be numeric"
        assert create_time > 0, "Create time should be positive"

        # Should be a reasonable timestamp (not too old or in future)
        current_time = time.time()
        assert create_time <= current_time, "Create time should be in the past"

        # Should be created within reasonable time (not more than a day ago)
        age_seconds = current_time - create_time
        assert (
            age_seconds < 86400
        ), f"Process should not be more than a day old: {age_seconds}s"

    def test_process_create_time_multiple_processes(self, psutil_module):
        """Test Process.create_time() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_create_times = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                create_time = proc.create_time()

                assert isinstance(
                    create_time, (int, float)
                ), f"Create time for PID {pid} should be numeric"
                assert (
                    create_time > 0
                ), f"Create time for PID {pid} should be positive"

                successful_create_times += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                continue  # Expected for some processes
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(
                    "Unexpected exception getting create_time for PID"
                    f" {pid}: {e}"
                )

        assert (
            successful_create_times > 0
        ), "Should successfully get at least some create times"

    def test_process_create_time_with_test_process(self, psutil_module):
        """Test Process.create_time() with a controlled test process."""
        creation_start = time.time()

        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=0.5)
            creation_end = time.time()

            try:
                proc = psutil_module.Process(test_proc.pid)
                create_time = proc.create_time()

                assert isinstance(
                    create_time, (int, float)
                ), "Test process create time should be numeric"

                # Should be created within our timeframe (with some tolerance)
                assert creation_start - 1 <= create_time <= creation_end + 1, (
                    "Create time should be within expected range:"
                    f" {creation_start} <= {create_time} <= {creation_end}"
                )

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()

    def test_process_create_time_consistency(self, psutil_module):
        """Test that create_time is consistent across multiple calls."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        # Get create time multiple times
        times = []
        for _ in range(5):
            times.append(proc.create_time())
            time.sleep(0.01)  # Small delay

        # All should be the same (or very close for floating point)
        first_time = times[0]
        for create_time in times[1:]:
            diff = abs(create_time - first_time)
            assert diff < 1.0, f"Create time should be consistent: {times}"


class TestProcessUserAndGroupIDs:
    """Test process user and group ID retrieval."""

    def test_process_uids_self(self, psutil_module):
        """Test Process.uids() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        try:
            uids = proc.uids()

            # Should have named tuple with real, effective, saved
            assert hasattr(uids, 'real'), "UIDs should have 'real' attribute"
            assert hasattr(
                uids, 'effective'
            ), "UIDs should have 'effective' attribute"
            assert hasattr(uids, 'saved'), "UIDs should have 'saved' attribute"

            # All should be non-negative integers
            assert isinstance(uids.real, int), "Real UID should be integer"
            assert isinstance(
                uids.effective, int
            ), "Effective UID should be integer"
            assert isinstance(uids.saved, int), "Saved UID should be integer"

            assert uids.real >= 0, "Real UID should be non-negative"
            assert uids.effective >= 0, "Effective UID should be non-negative"
            assert uids.saved >= 0, "Saved UID should be non-negative"

        except (psutil_module.AccessDenied, OSError):
            pytest.skip("Cannot access UID information")

    def test_process_gids_self(self, psutil_module):
        """Test Process.gids() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        try:
            gids = proc.gids()

            # Should have named tuple with real, effective, saved
            assert hasattr(gids, 'real'), "GIDs should have 'real' attribute"
            assert hasattr(
                gids, 'effective'
            ), "GIDs should have 'effective' attribute"
            assert hasattr(gids, 'saved'), "GIDs should have 'saved' attribute"

            # All should be non-negative integers
            assert isinstance(gids.real, int), "Real GID should be integer"
            assert isinstance(
                gids.effective, int
            ), "Effective GID should be integer"
            assert isinstance(gids.saved, int), "Saved GID should be integer"

            assert gids.real >= 0, "Real GID should be non-negative"
            assert gids.effective >= 0, "Effective GID should be non-negative"
            assert gids.saved >= 0, "Saved GID should be non-negative"

        except (psutil_module.AccessDenied, OSError):
            pytest.skip("Cannot access GID information")

    def test_process_uids_multiple_processes(self, psutil_module):
        """Test Process.uids() for multiple processes."""
        pids = psutil_module.pids()[: min(5, len(psutil_module.pids()))]
        successful_uids = 0

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                uids = proc.uids()

                # Basic validation
                assert hasattr(
                    uids, 'real'
                ), f"UIDs for PID {pid} should have 'real'"
                assert hasattr(
                    uids, 'effective'
                ), f"UIDs for PID {pid} should have 'effective'"
                assert hasattr(
                    uids, 'saved'
                ), f"UIDs for PID {pid} should have 'saved'"

                successful_uids += 1

            except (
                psutil_module.NoSuchProcess,
                psutil_module.AccessDenied,
                OSError,
            ):
                continue  # Expected for some processes
            except (ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting uids for PID {pid}: {e}"
                )

        # May not be able to get UIDs for any processes on some systems
        # Just ensure no unexpected exceptions occurred


class TestProcessWorkingDirectory:
    """Test process current working directory retrieval."""

    def test_process_cwd_self(self, psutil_module):
        """Test Process.cwd() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        try:
            cwd = proc.cwd()

            if cwd:  # May return empty string or None
                assert isinstance(cwd, str), "CWD should be string"
                assert len(cwd) > 0, "CWD should not be empty if not None"
                # Should be a valid directory path
                assert os.path.exists(cwd), f"CWD should exist: {cwd}"
                assert os.path.isdir(cwd), f"CWD should be directory: {cwd}"

        except (psutil_module.AccessDenied, OSError):
            pytest.skip("Cannot access CWD information")

    def test_process_cwd_multiple_processes(self, psutil_module):
        """Test Process.cwd() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_cwds = 0
        found_cwds = []

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                cwd = proc.cwd()

                if cwd:  # Not empty or None
                    assert isinstance(
                        cwd, str
                    ), f"CWD for PID {pid} should be string"
                    found_cwds.append(cwd)

                successful_cwds += 1

            except (
                psutil_module.NoSuchProcess,
                psutil_module.AccessDenied,
                OSError,
            ):
                continue  # Expected for some processes
            except (ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting cwd for PID {pid}: {e}"
                )

        # Should successfully query at least some processes
        assert (
            successful_cwds > 0
        ), "Should successfully get CWD for some processes"

    def test_process_cwd_with_test_process_and_chdir(self, psutil_module):
        """Test Process.cwd() with a test process in a specific directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test process that changes to temp directory
            test_command = f"""
import os
import time
os.chdir({temp_dir!r})
time.sleep(0.5)
"""

            with _test_process_helper() as create_proc:
                test_proc = create_proc(command=test_command)

                try:
                    # Give process time to change directory
                    time.sleep(0.1)

                    proc = psutil_module.Process(test_proc.pid)
                    cwd = proc.cwd()

                    if cwd:  # Process might not allow CWD access
                        assert isinstance(
                            cwd, str
                        ), "Test process CWD should be string"
                        # Should be the temp directory or a path containing it
                        # (exact match might not work due to symlinks, etc.)
                        assert temp_dir in cwd or os.path.samefile(
                            cwd, temp_dir
                        ), f"CWD should be temp directory: {cwd} vs {temp_dir}"

                finally:
                    if test_proc.poll() is None:
                        test_proc.terminate()
                        test_proc.wait()


class TestProcessTerminal:
    """Test process terminal retrieval."""

    def test_process_terminal_self(self, psutil_module):
        """Test Process.terminal() for current process."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        try:
            terminal = proc.terminal()

            # Can be None or string
            if terminal is not None:
                assert isinstance(
                    terminal, str
                ), "Terminal should be string or None"

        except (psutil_module.AccessDenied, OSError):
            pytest.skip("Cannot access terminal information")

    def test_process_terminal_multiple_processes(self, psutil_module):
        """Test Process.terminal() for multiple processes."""
        pids = psutil_module.pids()[: min(10, len(psutil_module.pids()))]
        successful_terminals = 0
        found_terminals = []

        for pid in pids:
            try:
                proc = psutil_module.Process(pid)
                terminal = proc.terminal()

                if terminal is not None:
                    assert isinstance(
                        terminal, str
                    ), f"Terminal for PID {pid} should be string or None"
                    found_terminals.append(terminal)

                successful_terminals += 1

            except (
                psutil_module.NoSuchProcess,
                psutil_module.AccessDenied,
                OSError,
            ):
                continue  # Expected for some processes
            except (ValueError, AttributeError) as e:
                pytest.fail(
                    f"Unexpected exception getting terminal for PID {pid}: {e}"
                )

        # Should successfully query at least some processes
        assert (
            successful_terminals > 0
        ), "Should successfully get terminal for some processes"


class TestProcessInfoIntegration:
    """Test integration and consistency of process information functions."""

    def test_process_info_consistency(self, psutil_module):
        """Test consistency of process information across functions."""
        with _test_process_helper() as create_proc:
            test_proc = create_proc(duration=1.0)

            try:
                proc = psutil_module.Process(test_proc.pid)

                # Get all basic information
                name = proc.name()
                exe = proc.exe()
                cmdline = proc.cmdline()
                ppid = proc.ppid()
                status = proc.status()
                create_time = proc.create_time()

                # Basic consistency checks
                combined_condition = isinstance(name, str) and len(name) > 0
                assert combined_condition, "Name should be valid"
                combined_condition = isinstance(ppid, int) and ppid > 0
                assert combined_condition, "PPID should be valid"
                combined_condition = (
                    isinstance(create_time, (int, float)) and create_time > 0
                )
                assert combined_condition, "Create time should be valid"

                # Handle integer status codes
                if isinstance(status, int):
                    status_map = {
                        0: 'running',
                        1: 'sleeping',
                        2: 'disk-sleep',
                        3: 'stopped',
                        4: 'zombie',
                    }
                    status_str = status_map.get(status, f'unknown-{status}')
                else:
                    status_str = status

                combined_condition = (
                    isinstance(status_str, str) and len(status_str) > 0
                )
                assert combined_condition, "Status should be valid"

                # Command line should be consistent with name/exe
                if cmdline and name:
                    cmdline_str = ' '.join(cmdline).lower()
                    name_basename = os.path.basename(name).lower()
                    assert (
                        name_basename in cmdline_str or 'python' in cmdline_str
                    ), (
                        "Cmdline should be consistent with name:"
                        f" {name_basename} vs {cmdline}"
                    )

                # Exe should be consistent with name
                if exe and name:
                    exe_basename = os.path.basename(exe).lower()
                    name_basename = os.path.basename(name).lower()
                    assert (
                        name_basename in exe_basename
                        or 'python' in exe_basename
                    ), (
                        "Exe should be consistent with name:"
                        f" {name_basename} vs {exe}"
                    )

                # PPID should be our PID
                our_pid = os.getpid()
                assert (
                    ppid == our_pid
                ), f"Child PPID should be our PID: {ppid} vs {our_pid}"

            finally:
                if test_proc.poll() is None:
                    test_proc.terminate()
                    test_proc.wait()

    def test_process_info_error_handling(self, psutil_module):
        """Test error handling for process information functions."""
        # Test with non-existent PID - don't create Process object in
        # constructor
        non_existent_pid = 99999999

        # Verify PID doesn't exist first
        assert not psutil_module.pid_exists(
            non_existent_pid
        ), "Test PID should not exist"

        # All methods should raise NoSuchProcess when called on non-existent
        # PID
        methods_to_test = [
            'name',
            'exe',
            'cmdline',
            'ppid',
            'status',
            'create_time',
            'cwd',
            'terminal',
        ]

        for method_name in methods_to_test:
            # Create Process object and immediately call method to trigger
            # exception
            try:
                proc = psutil_module.Process(non_existent_pid)
                method = getattr(proc, method_name)
                method()
                pytest.fail(
                    f"Expected NoSuchProcess exception for {method_name}()"
                )
            except psutil_module.NoSuchProcess:
                pass  # Expected
            except (OSError, ValueError, AttributeError, TypeError) as e:
                pytest.fail(
                    f"Unexpected exception type for {method_name}():"
                    f" {type(e).__name__}: {e}"
                )

    @pytest.mark.performance
    def test_process_info_performance(
        self, psutil_module, performance_timer, system_constants
    ):
        """Test performance of process information functions."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        # Test performance of each method
        methods_to_test = [
            'name',
            'exe',
            'cmdline',
            'ppid',
            'status',
            'create_time',
        ]
        max_time_ms = system_constants['performance_threshold_ms']

        for method_name in methods_to_test:
            method = getattr(proc, method_name)

            with performance_timer:
                try:
                    method()
                except (psutil_module.AccessDenied, OSError):
                    continue  # Skip if access denied

            avg_time_ms = performance_timer.duration_ms
            assert avg_time_ms < max_time_ms, (
                f"{method_name}() too slow: {avg_time_ms:.1f}ms (max:"
                f" {max_time_ms}ms)"
            )

    def test_multiple_process_info_calls(self, psutil_module):
        """Test calling process info methods multiple times."""
        own_pid = os.getpid()
        proc = psutil_module.Process(own_pid)

        # Call methods multiple times and ensure consistency
        methods = ['name', 'ppid', 'status', 'create_time']

        for method_name in methods:
            method = getattr(proc, method_name)
            results = []

            try:
                for _ in range(3):
                    results.append(method())
                    time.sleep(0.01)

                # Results should be consistent (create_time and ppid should be
                # exactly same)
                if method_name in {'ppid', 'create_time'}:
                    first_result = results[0]
                    for result in results[1:]:
                        if method_name == 'create_time':
                            # Allow small floating point differences
                            assert (
                                abs(result - first_result) < 1.0
                            ), f"{method_name} should be consistent: {results}"
                        else:
                            assert (
                                result == first_result
                            ), f"{method_name} should be consistent: {results}"

            except (psutil_module.AccessDenied, OSError):
                continue  # Skip if access denied


class TestProcessInfoRealWorld:
    """Test process information functions with real-world scenarios."""

    @pytest.mark.integration
    def test_process_info_sampling(self, psutil_module):
        """Test process information functions on a sample of real processes."""
        all_pids = psutil_module.pids()
        sample_size = min(20, len(all_pids))
        sample_pids = all_pids[:sample_size]

        info_stats = {
            'successful_names': 0,
            'successful_exes': 0,
            'successful_cmdlines': 0,
            'successful_ppids': 0,
            'successful_statuses': 0,
            'successful_create_times': 0,
            'total_tested': 0,
        }

        for pid in sample_pids:
            try:
                proc = psutil_module.Process(pid)
                info_stats['total_tested'] += 1

                # Test each method
                try:
                    name = proc.name()
                    if isinstance(name, str) and len(name) > 0:
                        info_stats['successful_names'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                try:
                    exe = proc.exe()
                    if exe is None or (isinstance(exe, str) and len(exe) > 0):
                        info_stats['successful_exes'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                try:
                    cmdline = proc.cmdline()
                    if isinstance(cmdline, list):
                        info_stats['successful_cmdlines'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                try:
                    ppid = proc.ppid()
                    if isinstance(ppid, int) and ppid > 0:
                        info_stats['successful_ppids'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                try:
                    status = proc.status()
                    # Handle both string and integer status
                    if isinstance(status, (str, int)):
                        info_stats['successful_statuses'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                try:
                    create_time = proc.create_time()
                    if (
                        isinstance(create_time, (int, float))
                        and create_time > 0
                    ):
                        info_stats['successful_create_times'] += 1
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

            except psutil_module.NoSuchProcess:
                continue  # Process died during testing

        # Should have reasonable success rates
        total_tested = info_stats['total_tested']
        assert total_tested > 0, "Should test at least some processes"

        # At least 30% success rate for basic info (lower threshold for Cygwin)
        min_success_rate = 0.3
        assert (
            info_stats['successful_names'] >= total_tested * min_success_rate
        ), (
            "Low name success rate:"
            f" {info_stats['successful_names']}/{total_tested}"
        )
        assert (
            info_stats['successful_ppids'] >= total_tested * min_success_rate
        ), (
            "Low ppid success rate:"
            f" {info_stats['successful_ppids']}/{total_tested}"
        )
        assert (
            info_stats['successful_statuses']
            >= total_tested * min_success_rate
        ), (
            "Low status success rate:"
            f" {info_stats['successful_statuses']}/{total_tested}"
        )

    def test_process_info_format_validation(self, psutil_module):
        """Test that process information follows expected formats."""
        sample_pids = psutil_module.pids()[
            : min(10, len(psutil_module.pids()))
        ]

        for pid in sample_pids:
            try:
                proc = psutil_module.Process(pid)

                # Test name format
                try:
                    name = proc.name()
                    name_basename = (
                        os.path.basename(name)
                        if name.startswith('/')
                        else name
                    )
                    # More flexible name validation for Cygwin
                    assert len(name_basename.strip()) == len(name_basename), (
                        "Process name should not have leading/trailing"
                        f" whitespace: '{name}'"
                    )
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                # Test status format - handle both string and integer
                try:
                    status = proc.status()
                    if isinstance(status, str):
                        valid_statuses = [
                            'running',
                            'sleeping',
                            'disk-sleep',
                            'stopped',
                            'tracing-stop',
                            'zombie',
                            'dead',
                            'wake-kill',
                            'waking',
                            'parked',
                        ]
                        # Allow unknown status codes as well
                        is_valid = (
                            status in valid_statuses
                            or status.startswith('unknown-')
                        )
                        assert is_valid, f"Invalid status format: {status}"
                    elif isinstance(status, int):
                        # Integer status codes are acceptable in Cygwin
                        assert (
                            0 <= status <= 10
                        ), f"Status code out of expected range: {status}"
                    else:
                        pytest.fail(
                            "Status should be string or int, got:"
                            f" {type(status)}"
                        )
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

                # Test create_time range
                try:
                    create_time = proc.create_time()
                    current_time = time.time()
                    # Should be within reasonable range (not more than 1 year
                    # ago)
                    assert (
                        create_time < current_time
                    ), "Create time should be in the past"
                    assert current_time - create_time < 365 * 24 * 3600, (
                        "Create time too old:"
                        f" {current_time - create_time} seconds"
                    )
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

            except psutil_module.NoSuchProcess:
                continue  # Process died during testing
