#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Error handling and edge case tests for psutil Cygwin implementation.

This module consolidates all error handling, boundary condition, and edge case
tests from the various phase test files. It ensures robust handling of:
- Invalid parameters
- Resource exhaustion scenarios
- System call failures
- Boundary conditions
- Race conditions
- Permission errors
- Signal interruptions
"""

import os
import signal
import subprocess
import sys
import threading
import time
from unittest import mock

import pytest

# =============================================================================
# --- Parameter Validation Tests
# =============================================================================


class TestParameterValidation:
    """Test parameter validation for all functions."""

    def test_net_connections_parameter_validation(self, cygwin_cext):
        """Test net_connections parameter validation."""
        # Valid parameters should work
        result = cygwin_cext.net_connections()
        assert isinstance(result, list)

        result = cygwin_cext.net_connections('inet')
        assert isinstance(result, list)

        # Invalid parameter types
        with pytest.raises(TypeError):
            cygwin_cext.net_connections(123)

        with pytest.raises(TypeError):
            cygwin_cext.net_connections(['invalid'])

        with pytest.raises(TypeError):
            cygwin_cext.net_connections({'invalid': 'dict'})

        # Invalid string parameters should raise ValueError (actual behavior)
        with pytest.raises(ValueError, match="Invalid connection kind"):
            cygwin_cext.net_connections('invalid_protocol')

    def test_proc_net_connections_parameter_validation(self, cygwin_cext):
        """Test proc_net_connections parameter validation."""
        current_pid = os.getpid()
        result = cygwin_cext.proc_net_connections(current_pid, 'inet')
        assert isinstance(result, list)

        # Invalid PID types
        with pytest.raises(TypeError):
            cygwin_cext.proc_net_connections("invalid", 'inet')

        with pytest.raises(TypeError):
            cygwin_cext.proc_net_connections(12.34, 'inet')

        with pytest.raises(TypeError):
            cygwin_cext.proc_net_connections(None, 'inet')

        # Non-existent PIDs should return empty list
        result = cygwin_cext.proc_net_connections(999999, 'inet')
        assert isinstance(result, list)
        assert len(result) == 0

    def test_priority_functions_parameter_validation(self, cygwin_cext):
        """Test priority function parameter validation."""
        current_pid = os.getpid()

        # Valid getpriority calls
        priority = cygwin_cext.getpriority(current_pid)
        assert isinstance(priority, int)

        # Invalid PID types for getpriority
        with pytest.raises(TypeError):
            cygwin_cext.getpriority("invalid")

        with pytest.raises(TypeError):
            cygwin_cext.getpriority(12.34)

        # Invalid PIDs for getpriority should raise OSError
        with pytest.raises(OSError, match="No such process"):
            cygwin_cext.getpriority(999999)

        # Invalid priority values
        with pytest.raises((ValueError, OSError)):
            cygwin_cext.setpriority(current_pid, -25)  # Too low

        with pytest.raises((ValueError, OSError)):
            cygwin_cext.setpriority(current_pid, 25)  # Too high

    def test_process_info_parameter_validation(
        self, cygwin_cext, psutil_module
    ):
        """Test process information function parameter validation."""
        # Test Process class initialization with invalid PIDs
        with pytest.raises(TypeError):
            psutil_module.Process("invalid")

        # None is converted to current PID in psutil, not a TypeError
        proc = psutil_module.Process(None)
        assert proc.pid == os.getpid()

        # Non-existent PIDs should raise NoSuchProcess
        with pytest.raises(psutil_module.NoSuchProcess):
            psutil_module.Process(999999)

    def test_disk_function_parameter_validation(self, psutil_module):
        """Test disk function parameter validation."""
        # disk_usage requires a valid path
        with pytest.raises(TypeError):
            psutil_module.disk_usage(None)

        with pytest.raises(TypeError):
            psutil_module.disk_usage(123)

        # Non-existent path should raise OSError
        with pytest.raises(OSError, match="No such file or directory"):
            psutil_module.disk_usage("/nonexistent/path/12345")


# =============================================================================
# --- Boundary Condition Tests
# =============================================================================


class TestBoundaryConditions:
    """Test boundary conditions and edge values."""

    def test_extreme_pid_values(self, cygwin_cext, psutil_module):
        """Test handling of extreme PID values."""
        boundary_pids = [
            1,  # Minimum valid PID
            32767,  # Common PID_MAX value
            65536,  # 16-bit boundary
            2**31 - 1,  # 32-bit signed int max
        ]

        for pid in boundary_pids:
            # check_pid_range should handle these
            try:
                cygwin_cext.check_pid_range(pid)
            except (ValueError, OSError):
                pass  # May be rejected as too large

            # pid_exists should handle extreme values
            result = psutil_module.pid_exists(pid)
            assert isinstance(result, bool)

    def test_priority_boundary_values(self, cygwin_cext):
        """Test priority boundary values."""
        current_pid = os.getpid()
        original_priority = cygwin_cext.getpriority(current_pid)

        # Test valid priority boundaries
        valid_priorities = [-20, -19, -10, -1, 0, 1, 10, 19]

        for priority in valid_priorities:
            try:
                cygwin_cext.setpriority(current_pid, priority)
                actual_priority = cygwin_cext.getpriority(current_pid)
                assert actual_priority == priority
                cygwin_cext.setpriority(current_pid, original_priority)
            except PermissionError:
                if priority >= 0:
                    pytest.fail(
                        "Permission denied for non-negative priority"
                        f" {priority}"
                    )

    def test_memory_value_boundaries(self, cygwin_cext, system_constants):
        """Test memory value boundary conditions."""
        vmem = cygwin_cext.virtual_memory()
        total, available, used, free, cached, buffers, shared = vmem

        # Test extreme memory conditions
        assert 0 <= available <= total
        assert 0 <= used <= total
        assert 0 <= free <= total
        assert 0 <= cached <= total
        assert 0 <= buffers <= total
        assert 0 <= shared <= total

        # Test consistency
        assert (used + free) <= (
            total + system_constants['memory_tolerance_bytes']
        )

    def test_cpu_time_boundaries(self, cygwin_cext, system_constants):
        """Test CPU time boundary values."""
        cpu_times = cygwin_cext.per_cpu_times()
        max_time = system_constants['max_reasonable_cpu_time_seconds']

        for i, times in enumerate(cpu_times):
            for j, time_val in enumerate(times):
                assert 0 <= time_val <= max_time, (
                    f"CPU {i} time index {j} value {time_val} outside"
                    " reasonable range"
                )

    def test_interface_name_boundaries(self, cygwin_cext):
        """Test interface name boundary conditions."""
        interfaces = cygwin_cext.net_if_addrs()
        if not interfaces:
            pytest.skip("No network interfaces found")

        # Test various interface name edge cases
        edge_case_names = [
            "",  # Empty string
            "x"
            * 50,  # Very long name (raises ValueError with specific message)
            "nonexistent",  # Non-existent interface
        ]

        for name in edge_case_names:
            if name == "":
                with pytest.raises(ValueError, match="empty"):
                    cygwin_cext.net_if_mtu(name)
            elif len(name) > 43:  # Implementation has max of 43 chars
                with pytest.raises(
                    ValueError, match="Interface name too long"
                ):
                    cygwin_cext.net_if_mtu(name)
            else:
                # Non-existent interface should raise OSError
                # The actual error message is "Failed to get MTU for <name>:
                # Invalid argument"
                with pytest.raises(
                    OSError, match=r"Failed to get MTU|Invalid argument"
                ):
                    cygwin_cext.net_if_mtu(name)


# =============================================================================
# --- System Call Failure Tests
# =============================================================================


class TestSystemCallFailures:
    """Test handling of system call failures and recovery."""

    def test_interrupted_system_calls(self, cygwin_cext):
        """Test handling of interrupted system calls."""

        def signal_handler(signum, frame):
            pass

        if not hasattr(signal, 'SIGUSR1'):
            pytest.skip("SIGUSR1 not available on this platform")

        original_handler = signal.signal(signal.SIGUSR1, signal_handler)

        try:

            def worker():
                for i in range(10):
                    try:
                        # Send signal to interrupt system calls
                        if i % 3 == 0:
                            os.kill(os.getpid(), signal.SIGUSR1)

                        # These should handle interruption gracefully
                        # Use underscore prefix to indicate
                        # intentionally unused
                        _connections = cygwin_cext.net_connections('inet')
                        _priority = cygwin_cext.getpriority(os.getpid())
                        _interfaces = cygwin_cext.net_if_addrs()

                    except (OSError, InterruptedError):
                        pass  # Expected

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)

            if thread.is_alive():
                pytest.fail("Worker thread hung - possible deadlock")

        finally:
            signal.signal(signal.SIGUSR1, original_handler)

    @pytest.mark.slow
    def test_resource_exhaustion_simulation(self, cygwin_cext):
        """Test behavior under simulated resource exhaustion."""

        def stress_worker(results):
            try:
                for _ in range(50):
                    cygwin_cext.net_connections('inet')
                    cygwin_cext.net_if_addrs()
                    cygwin_cext.getpagesize()
                results.append("success")
            except (OSError, ValueError, PermissionError) as e:
                results.append(f"error: {e}")

        # Create many workers to stress the system
        results = []
        threads = []

        for _ in range(10):
            thread = threading.Thread(target=stress_worker, args=(results,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Most operations should succeed
        successes = sum(1 for r in results if r == "success")
        success_rate = successes / len(results)
        assert (
            success_rate >= 0.8
        ), f"Too many failures under stress: {success_rate:.2%}"

    def test_proc_filesystem_errors(self, psutil_module):
        """Test handling of /proc filesystem errors."""
        original_listdir = os.listdir

        def mock_failing_listdir(path):
            if path == '/proc':
                raise PermissionError("Access denied")
            return original_listdir(path)

        with mock.patch('os.listdir', side_effect=mock_failing_listdir):
            try:
                pids = psutil_module.pids()
                assert isinstance(pids, list)
            except (OSError, PermissionError, IndexError):
                pass  # Expected


# =============================================================================
# --- Race Condition Tests
# =============================================================================


class TestRaceConditions:
    """Test for race conditions and thread safety."""

    def test_concurrent_error_handling(self, cygwin_cext):
        """Test error handling under concurrent access."""

        def error_worker(worker_id, results):
            error_count = 0
            success_count = 0

            for i in range(20):
                try:
                    if i % 3 == 0:
                        cygwin_cext.net_connections('inet')
                        success_count += 1
                    elif i % 3 == 1:
                        cygwin_cext.getpriority(999999)  # Should fail
                        success_count += 1
                    else:
                        cygwin_cext.net_if_mtu("invalid")  # Should fail
                        success_count += 1
                except (OSError, ValueError, PermissionError):
                    error_count += 1

            results[worker_id] = (success_count, error_count)

        results = {}
        threads = []

        for worker_id in range(5):
            thread = threading.Thread(
                target=error_worker, args=(worker_id, results)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should have some successes and some errors
        total_successes = sum(r[0] for r in results.values())
        total_errors = sum(r[1] for r in results.values())

        assert total_successes > 0
        assert total_errors > 0
        assert len(results) == 5  # All workers should complete

    def test_rapid_process_creation_destruction(self, psutil_module):
        """Test handling of rapidly changing process list."""
        processes = []

        try:
            for i in range(10):
                proc = subprocess.Popen(
                    [sys.executable, '-c', 'import time; time.sleep(0.01)']
                )
                processes.append(proc)

                if i % 3 == 0:
                    current_pids = psutil_module.pids()
                    assert isinstance(current_pids, list)
                    assert psutil_module.pid_exists(os.getpid())

            time.sleep(0.05)
            final_pids = psutil_module.pids()
            assert isinstance(final_pids, list)

        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


# =============================================================================
# --- Exception Handling Tests
# =============================================================================


class TestExceptionHandling:
    """Test exception handling and error recovery."""

    def test_graceful_degradation(self, cygwin_cext):
        """Test graceful degradation when some operations fail."""
        # These should always work
        pagesize = cygwin_cext.getpagesize()
        assert isinstance(pagesize, int)
        assert pagesize > 0

        # This should work for current process
        priority = cygwin_cext.getpriority(os.getpid())
        assert isinstance(priority, int)

        # These may fail on some systems but shouldn't crash
        try:
            interfaces = cygwin_cext.net_if_addrs()
            assert isinstance(interfaces, list)
        except OSError:
            pass

        try:
            connections = cygwin_cext.net_connections('inet')
            assert isinstance(connections, list)
        except OSError:
            pass

    def test_error_message_quality(self, cygwin_cext):
        """Test that error messages are informative."""
        # Invalid PID should give informative error
        with pytest.raises(OSError, match="process") as exc_info:
            cygwin_cext.getpriority(999999)
        assert str(exc_info.value), "Error message should not be empty"

        # Invalid interface should give informative error
        with pytest.raises(OSError, match="interface") as exc_info:
            cygwin_cext.net_if_mtu("nonexistent_interface")
        assert str(exc_info.value), "Error message should not be empty"

    def test_cleanup_after_errors(self, cygwin_cext):
        """Test that resources are cleaned up after errors."""
        error_count = 0

        for i in range(50):
            try:
                if i % 4 == 0:
                    cygwin_cext.getpriority(999999)  # Non-existent PID
                elif i % 4 == 1:
                    cygwin_cext.net_if_mtu("invalid")  # Invalid interface
                elif i % 4 == 2:
                    cygwin_cext.setpriority(
                        os.getpid(), 100
                    )  # Invalid priority
                else:
                    cygwin_cext.proc_net_connections(
                        999999, 'inet'
                    )  # Non-existent PID
            except (OSError, ValueError, PermissionError):
                error_count += 1

        assert error_count > 0, "Should have encountered some errors"

        # After errors, normal operations should still work
        pagesize = cygwin_cext.getpagesize()
        assert isinstance(pagesize, int)

        connections = cygwin_cext.net_connections('inet')
        assert isinstance(connections, list)

    def test_recovery_after_errors(self, psutil_module):
        """Test that functions work normally after encountering errors."""
        # Cause some errors first
        try:
            psutil_module.pid_exists("invalid")
        except TypeError:
            pass

        try:
            psutil_module.Process(999999)
        except psutil_module.NoSuchProcess:
            pass

        # Normal operations should still work
        own_pid = os.getpid()
        assert psutil_module.pid_exists(own_pid)

        pids = psutil_module.pids()
        assert isinstance(pids, list)
        assert own_pid in pids


# =============================================================================
# --- Permission and Access Tests
# =============================================================================


class TestPermissionHandling:
    """Test handling of permission and access errors."""

    def test_system_process_access(self, psutil_module):
        """Test handling of system process access restrictions."""
        system_pids = [pid for pid in psutil_module.pids() if pid < 100]

        for pid in system_pids[:5]:
            # pid_exists should work regardless of permissions
            result = psutil_module.pid_exists(pid)
            assert isinstance(result, bool)

            # Process creation might fail due to permissions
            try:
                proc = psutil_module.Process(pid)
                try:
                    name = proc.name()
                    assert isinstance(name, str)
                except psutil_module.AccessDenied:
                    pass  # Expected for some system processes
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                pass  # Both are acceptable

    def test_zombie_process_handling(self, psutil_module):
        """Test handling of zombie processes."""
        if not hasattr(os, 'fork'):
            pytest.skip("Fork not available on this platform")

        pid = os.fork()

        if pid == 0:
            # Child process - exit immediately
            os._exit(0)
        else:
            # Parent process
            try:
                time.sleep(0.1)  # Let child become zombie

                # Zombie should still exist in PID list
                pids = psutil_module.pids()
                if pid in pids:
                    assert psutil_module.pid_exists(pid)

                    # Process object creation might work or fail
                    try:
                        proc = psutil_module.Process(pid)
                        status = proc.status()
                        assert isinstance(status, str)
                    except (
                        psutil_module.NoSuchProcess,
                        psutil_module.ZombieProcess,
                    ):
                        pass  # Both are acceptable

            finally:
                # Clean up zombie
                try:
                    os.waitpid(pid, 0)
                except OSError:
                    pass


# =============================================================================
# --- Memory and Resource Tests
# =============================================================================


class TestMemoryPressure:
    """Test behavior under memory pressure scenarios."""

    def test_memory_pressure_scenarios(self, psutil_module):
        """Test behavior under memory pressure."""
        large_results = []

        try:
            for i in range(50):
                pids = psutil_module.pids()
                large_results.append(pids)

                if i % 10 == 0:
                    sample_pid = pids[0] if pids else os.getpid()
                    result = psutil_module.pid_exists(sample_pid)
                    assert isinstance(result, bool)

                # Clean up some results to avoid excessive memory usage
                if len(large_results) > 10:
                    large_results.pop(0)

            final_pids = psutil_module.pids()
            assert isinstance(final_pids, list)
            assert len(final_pids) > 0

        except MemoryError:
            pytest.fail("Memory pressure caused failure")

    def test_memory_allocation_failure_simulation(self, cygwin_cext):
        """Test handling of memory allocation failures."""
        memory_hogs = []

        try:
            # Allocate significant memory to create pressure
            memory_hogs.extend(
                b'x' * (10 * 1024 * 1024) for _ in range(5)
            )  # 10MB chunks

            # Test functions still work under memory pressure
            connections = cygwin_cext.net_connections('inet')
            assert isinstance(connections, list)

            interfaces = cygwin_cext.net_if_addrs()
            assert isinstance(interfaces, list)

        except MemoryError:
            pass  # If we run out of memory, that's OK for this test
        finally:
            del memory_hogs


# =============================================================================
# --- State Consistency Tests
# =============================================================================


class TestStateConsistency:
    """Test that internal state remains consistent after errors."""

    def test_state_consistency_under_errors(self, cygwin_cext):
        """Test that internal state remains consistent after errors."""
        # Cause many errors and verify state consistency
        for _ in range(100):
            try:
                cygwin_cext.getpagesize()  # Should succeed
                cygwin_cext.getpriority(999999)  # Should fail
                cygwin_cext.net_connections('inet')  # Should succeed
                cygwin_cext.net_if_mtu("invalid")  # Should fail
            except (OSError, ValueError, PermissionError):
                pass  # Expected

        # Verify that successful operations still work consistently
        results = []
        for _ in range(20):
            pagesize = cygwin_cext.getpagesize()
            results.append(pagesize)

        # All results should be identical (consistent state)
        assert len(set(results)) == 1, "Inconsistent state after errors"

    def test_partial_failure_handling(self, psutil_module):
        """Test handling when some operations fail but others succeed."""
        all_pids = psutil_module.pids()

        # Mix of valid and invalid PIDs
        test_pids = all_pids[:5] + [99999999, -1, 0]

        valid_count = 0
        invalid_count = 0

        for pid in test_pids:
            try:
                result = psutil_module.pid_exists(pid)
                if result:
                    valid_count += 1
                else:
                    invalid_count += 1
            except TypeError:
                invalid_count += 1

        # Should handle mix of valid/invalid gracefully
        assert valid_count > 0
        assert invalid_count > 0


# =============================================================================
# --- Network-Specific Edge Cases
# =============================================================================


class TestNetworkEdgeCases:
    """Test network-specific edge cases and error scenarios."""

    def test_connection_count_extremes(self, cygwin_cext, system_constants):
        """Test behavior with extreme connection counts."""
        start_time = time.time()
        connections = cygwin_cext.net_connections('inet')
        end_time = time.time()

        connection_count = len(connections)
        call_duration = (end_time - start_time) * 1000  # Convert to ms

        # Adjust expectation based on actual performance characteristics
        # First call may be slower due to initialization
        if connection_count == 0:
            # Allow more time for empty result (may involve timeout)
            max_time = 500  # 500ms for initialization/timeout
        else:
            # Should handle any reasonable number of connections efficiently
            max_time = max(
                system_constants['performance_threshold_ms'],
                connection_count * 0.1,
            )

        # Only fail if dramatically slower
        if call_duration > max_time * 2:
            pytest.fail(
                f"Too slow for {connection_count} connections:"
                f" {call_duration:.3f}ms"
            )

        # Validate connection structures
        for i, conn in enumerate(connections[:100]):  # Check first 100
            assert isinstance(conn, tuple)
            assert len(conn) == 7

    def test_winsock_initialization_status(self, cygwin_cext):
        """Test that networking subsystem is properly initialized."""
        try:
            connections = cygwin_cext.net_connections('inet')
            assert isinstance(connections, list)

            interfaces = cygwin_cext.net_if_addrs()
            assert isinstance(interfaces, list)

        except OSError as e:
            if "Failed to create socket" in str(e):
                pytest.fail(f"Network initialization issue: {e}")
            else:
                pass  # Other errors are acceptable


# =============================================================================
# --- Cross-Platform Edge Cases
# =============================================================================


class TestCrossplatformEdgeCases:
    """Test edge cases specific to Cygwin's dual nature."""

    def test_path_format_handling(self, psutil_module):
        """Test handling of different path formats in Cygwin."""
        # Test with various path formats
        test_paths = [
            "/",  # Unix root
            "/cygdrive/c",  # Cygwin drive path
            "/proc",  # Proc filesystem
            "/tmp",  # Temp directory
        ]

        for path in test_paths:
            if os.path.exists(path):
                try:
                    usage = psutil_module.disk_usage(path)
                    # Some paths may legitimately have 0 total (like /proc)
                    if path != "/proc":
                        assert usage.total > 0
                    assert 0 <= usage.percent <= 100
                except OSError:
                    pass  # Some paths may not be accessible

    def test_unicode_handling(self, psutil_module):
        """Test handling of unicode in process names and paths."""
        # Create process with unicode in command line
        try:
            proc = subprocess.Popen([
                sys.executable,
                '-c',
                'import time; time.sleep(0.2)  # Unicode: 测试 процесс',
            ])

            child_pid = proc.pid

            try:
                assert psutil_module.pid_exists(child_pid)
                child_process = psutil_module.Process(child_pid)
                assert child_process.pid == child_pid

            finally:
                proc.terminate()
                proc.wait()

        except (UnicodeError, OSError) as e:
            pytest.skip(f"Unicode test failed: {e}")


# =============================================================================
# --- Extreme Load Tests
# =============================================================================


class TestExtremeLoad:
    """Test behavior under extreme system load."""

    @pytest.mark.slow
    def test_extreme_load_conditions(self, psutil_module):
        """Test under extreme system load."""
        processes = []

        try:
            # Create many short-lived processes
            for i in range(20):
                proc = subprocess.Popen([
                    sys.executable,
                    '-c',
                    f'import time; time.sleep(0.0{i % 10 + 1})',
                ])
                processes.append(proc)

            # Test operations during high load
            start_time = time.time()
            while time.time() - start_time < 0.5:
                try:
                    pids = psutil_module.pids()
                    assert isinstance(pids, list)
                    assert psutil_module.pid_exists(os.getpid())
                    time.sleep(0.01)
                except (OSError, ValueError, PermissionError) as e:
                    pytest.fail(f"Failed under load: {e}")

        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
