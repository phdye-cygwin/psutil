#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cygwin Process Enumeration and Management Tests

This module tests process enumeration and management functions:
- pids() - List all process IDs
- pid_exists() - Check if a process exists
- Process signal methods and lifecycle management

Migrated from:
- issue/phase-3/tests/test_phase3_1_process_enumeration.py
- issue/phase-3/tests/test_phase3.py (process enumeration parts)

Functions tested:
- psutil.pids()
- psutil.pid_exists()
- Basic Process lifecycle operations

This is part of lap 6 of the test reorganization plan.
"""

import os
import subprocess
import sys
import threading
import time
import tracemalloc

import pytest


class TestProcessEnumeration:
    """Test process enumeration functions."""

    def test_pids_basic_functionality(self, psutil_module):
        """Test psutil.pids() basic functionality."""
        pids = psutil_module.pids()

        # Should return a list
        assert isinstance(pids, list), "pids() should return a list"

        # Should have at least some processes
        assert len(pids) > 0, "Should find at least one process"

        # All entries should be positive integers
        for pid in pids:
            assert isinstance(pid, int), f"PID {pid} is not an integer"
            assert pid > 0, f"PID {pid} is not positive"

    def test_pids_includes_own_process(self, psutil_module):
        """Test that pids() includes our own PID."""
        own_pid = os.getpid()
        pids = psutil_module.pids()
        assert own_pid in pids, f"Own PID {own_pid} should be in pids() list"

    def test_pids_includes_parent_process(self, psutil_module):
        """Test that pids() includes parent PID."""
        parent_pid = os.getppid()
        pids = psutil_module.pids()
        assert (
            parent_pid in pids
        ), f"Parent PID {parent_pid} should be in pids() list"

    def test_pids_uniqueness(self, psutil_module):
        """Test that pids() returns unique PIDs."""
        pids = psutil_module.pids()
        unique_pids = set(pids)
        assert len(pids) == len(
            unique_pids
        ), f"Duplicate PIDs found: {len(pids)} != {len(unique_pids)}"

    def test_pids_consistency_with_proc(self, psutil_module):
        """Test pids() consistency with direct /proc parsing."""
        if not os.path.exists('/proc'):
            pytest.skip("/proc filesystem not available")

        # Get PIDs from psutil
        psutil_pids = set(psutil_module.pids())

        # Get PIDs from direct /proc parsing
        proc_pids = set()
        try:
            for entry in os.listdir('/proc'):
                if entry.isdigit():
                    proc_pids.add(int(entry))
        except OSError:
            pytest.skip("Cannot read /proc directory")

        # Calculate overlap
        common_pids = psutil_pids & proc_pids
        total_unique = len(psutil_pids | proc_pids)
        overlap_ratio = (
            len(common_pids) / total_unique if total_unique > 0 else 0
        )

        # Should have significant overlap (allow for race conditions)
        assert overlap_ratio > 0.9, (
            "Poor overlap between psutil.pids() and /proc: "
            f"{len(common_pids)}/{total_unique} "
            f"(overlap: {overlap_ratio:.2f})"
        )

    @pytest.mark.performance
    def test_pids_performance(
        self, psutil_module, performance_timer, system_constants
    ):
        """Test pids() performance."""
        iterations = 10

        with performance_timer:
            for _ in range(iterations):
                pids = psutil_module.pids()

        avg_time_ms = performance_timer.duration_ms / iterations
        max_time_ms = system_constants['performance_threshold_ms']

        assert avg_time_ms < max_time_ms, (
            f"pids() too slow: {avg_time_ms:.1f}ms average "
            f"(max: {max_time_ms}ms)"
        )

        # Should return consistent results
        assert len(pids) > 0


class TestPidExists:
    """Test pid_exists() function."""

    def test_pid_exists_basic_functionality(self, psutil_module):
        """Test basic pid_exists() functionality."""
        own_pid = os.getpid()
        parent_pid = os.getppid()

        # Should return True for our own PID
        assert psutil_module.pid_exists(
            own_pid
        ), f"Own PID {own_pid} should exist"

        # Should return True for parent PID
        assert psutil_module.pid_exists(
            parent_pid
        ), f"Parent PID {parent_pid} should exist"

        # Should return boolean type
        result = psutil_module.pid_exists(own_pid)
        assert isinstance(result, bool), "pid_exists() should return boolean"

    def test_pid_exists_invalid_pids(self, psutil_module):
        """Test pid_exists() with invalid PIDs."""
        # Negative PID
        assert not psutil_module.pid_exists(
            -1
        ), "Negative PID should not exist"

        # Zero PID - on some systems PID 0 might exist (kernel), but generally
        # not accessible
        assert not psutil_module.pid_exists(0), "PID 0 should not exist"

        # Very large PID (unlikely to exist)
        assert not psutil_module.pid_exists(
            99999999
        ), "Large PID should not exist"

    def test_pid_exists_type_validation(self, psutil_module):
        """Test pid_exists() input type validation."""
        # Should raise TypeError for non-integer input
        with pytest.raises(TypeError):
            psutil_module.pid_exists("invalid")

        with pytest.raises(TypeError):
            psutil_module.pid_exists(None)

        with pytest.raises(TypeError):
            psutil_module.pid_exists([123])

    def test_pid_exists_consistency_with_pids(self, psutil_module):
        """Test consistency between pid_exists() and pids()."""
        all_pids = psutil_module.pids()

        # Test a sample of PIDs (not all to avoid performance issues)
        sample_size = min(50, len(all_pids))
        sample_pids = all_pids[:sample_size]

        inconsistencies = 0
        for pid in sample_pids:
            exists = psutil_module.pid_exists(pid)
            if not exists:
                # Process might have died - double check
                time.sleep(0.001)
                exists = psutil_module.pid_exists(pid)
                if not exists:
                    inconsistencies += 1

        # Allow up to 10% inconsistencies due to race conditions
        max_inconsistencies = max(1, sample_size // 10)
        assert inconsistencies <= max_inconsistencies, (
            "Too many inconsistencies between pids() and pid_exists(): "
            f"{inconsistencies}/{sample_size}"
        )

    @pytest.mark.performance
    def test_pid_exists_performance(
        self, psutil_module, performance_timer, system_constants
    ):
        """Test pid_exists() performance."""
        own_pid = os.getpid()
        iterations = 1000

        with performance_timer:
            for _ in range(iterations):
                result = psutil_module.pid_exists(own_pid)
                assert result, "Own PID should always exist during test"

        avg_time_ms = performance_timer.duration_ms / iterations
        max_time_ms = 1.0  # pid_exists should be very fast

        assert avg_time_ms < max_time_ms, (
            f"pid_exists() too slow: {avg_time_ms:.3f}ms average "
            f"(max: {max_time_ms}ms)"
        )


class TestProcessLifecycle:
    """Test process lifecycle and short-lived processes."""

    def test_short_lived_process(self, psutil_module):
        """Test behavior with short-lived processes."""
        # Create a short-lived subprocess
        proc = subprocess.Popen(
            [sys.executable, '-c', 'import time; time.sleep(0.1)']
        )
        child_pid = proc.pid

        try:
            # Should exist initially
            assert psutil_module.pid_exists(
                child_pid
            ), f"Child PID {child_pid} should exist initially"

            # Should be in pids() list (if we're quick enough)
            current_pids = psutil_module.pids()
            if child_pid in current_pids:
                # If it's in the list, pid_exists should confirm it
                assert psutil_module.pid_exists(
                    child_pid
                ), "Consistency check failed"

            # Wait for process to complete
            proc.wait()

            # Give system a moment to clean up
            time.sleep(0.05)

            # May or may not exist now due to cleanup timing
            # Just ensure no exceptions are raised
            result = psutil_module.pid_exists(child_pid)
            assert isinstance(
                result, bool
            ), "pid_exists() should return boolean even after process death"

        finally:
            # Ensure cleanup
            if proc.poll() is None:
                proc.terminate()
                proc.wait()

    def test_multiple_process_creation(self, psutil_module):
        """Test behavior under process creation load."""
        processes = []
        pids_seen = set()

        try:
            # Create multiple short-lived processes rapidly
            for i in range(10):
                proc = subprocess.Popen([
                    sys.executable,
                    '-c',
                    f'import time; time.sleep(0.{i + 1})',
                ])
                processes.append(proc)
                pids_seen.add(proc.pid)

            # Get current PIDs
            current_pids = set(psutil_module.pids())

            # At least some of our processes should be visible
            overlap = pids_seen & current_pids
            assert len(overlap) > 0, "No child processes found in pids()"

            # Verify pid_exists() for visible processes
            for pid in overlap:
                assert psutil_module.pid_exists(
                    pid
                ), f"pid_exists() failed for visible PID {pid}"

        finally:
            # Clean up all processes
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


class TestProcessIntegration:
    """Test integration with psutil.Process objects."""

    def test_integration_with_process_objects(self, psutil_module):
        """Test integration with psutil.Process objects."""
        pids = psutil_module.pids()
        sample_pids = pids[: min(10, len(pids))]

        successful_processes = 0
        for pid in sample_pids:
            try:
                # Should be able to create Process object
                proc = psutil_module.Process(pid)

                # Should be able to get basic info
                name = proc.name()
                assert isinstance(
                    name, str
                ), f"Process name should be string for PID {pid}"

                # pid_exists should be consistent
                assert psutil_module.pid_exists(
                    pid
                ), f"pid_exists() inconsistent for PID {pid}"

                successful_processes += 1

            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                # Expected for some processes
                pass
            except (OSError, ValueError, AttributeError) as e:
                pytest.fail(f"Unexpected exception for PID {pid}: {e}")

        # Should successfully create at least some Process objects
        assert successful_processes > 0, "Could not create any Process objects"

    def test_process_enumeration_consistency(self, psutil_module):
        """Test consistency between enumeration functions and Process
        objects.
        """
        own_pid = os.getpid()
        parent_pid = os.getppid()

        # Test own process
        assert psutil_module.pid_exists(own_pid), "Own PID should exist"
        own_process = psutil_module.Process(own_pid)
        assert own_process.pid == own_pid, "Process object PID should match"

        # Test parent process
        assert psutil_module.pid_exists(parent_pid), "Parent PID should exist"
        parent_process = psutil_module.Process(parent_pid)
        assert (
            parent_process.pid == parent_pid
        ), "Parent process object PID should match"

        # Both should be in pids() list
        all_pids = psutil_module.pids()
        assert own_pid in all_pids, "Own PID should be in pids() list"
        assert parent_pid in all_pids, "Parent PID should be in pids() list"


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_error_recovery(self, psutil_module):
        """Test error handling and recovery."""
        # Test with various invalid inputs
        invalid_inputs = [-1, 0, 99999999]

        for invalid_pid in invalid_inputs:
            result = psutil_module.pid_exists(invalid_pid)
            assert isinstance(
                result, bool
            ), f"Should return boolean for invalid PID {invalid_pid}"
            assert not result, f"Invalid PID {invalid_pid} should not exist"

        # Ensure normal functionality still works after errors
        own_pid = os.getpid()
        assert psutil_module.pid_exists(
            own_pid
        ), "Normal functionality should work after errors"

        pids = psutil_module.pids()
        assert own_pid in pids, "pids() should work after errors"

    def test_concurrent_access(self, psutil_module):
        """Test concurrent access to pids() and pid_exists()."""
        import queue

        results = queue.Queue()
        errors = queue.Queue()

        def worker():
            try:
                own_pid = os.getpid()
                for _ in range(10):
                    pids = psutil_module.pids()
                    results.put(len(pids))

                    # Test pid_exists for our own PID
                    exists = psutil_module.pid_exists(own_pid)
                    results.put(exists)
            except (OSError, ValueError, AttributeError, RuntimeError) as e:
                errors.put(e)

        # Start multiple threads
        threads = []
        for _ in range(5):
            t = threading.Thread(target=worker)
            t.start()
            threads.append(t)

        # Wait for completion
        for t in threads:
            t.join()

        # Check for errors
        error_list = []
        while not errors.empty():
            error_list.append(errors.get())

        assert len(error_list) == 0, f"Concurrent access errors: {error_list}"

        # Check results
        assert results.qsize() > 0, "No results from concurrent access test"

        # Validate results
        pid_counts = []
        existence_checks = []
        while not results.empty():
            result = results.get()
            if isinstance(result, int):
                pid_counts.append(result)
            elif isinstance(result, bool):
                existence_checks.append(result)

        assert all(
            count > 0 for count in pid_counts
        ), "All PID counts should be positive"
        assert all(
            existence_checks
        ), "All existence checks for own PID should be True"

    @pytest.mark.slow
    def test_memory_usage(self, psutil_module):
        """Test memory usage of pids() function."""
        tracemalloc.start()

        # Get baseline
        baseline_snapshot = tracemalloc.take_snapshot()

        # Run pids() multiple times
        for _ in range(100):
            pids = psutil_module.pids()
            del pids  # Explicit cleanup

        # Check memory usage
        final_snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Calculate memory usage
        top_stats = final_snapshot.compare_to(baseline_snapshot, 'lineno')
        total_memory_mb = sum(stat.size for stat in top_stats) / 1024 / 1024

        # Should not use excessive memory (allow up to 10MB)
        assert (
            total_memory_mb < 10.0
        ), f"Excessive memory usage: {total_memory_mb:.2f}MB"


class TestSystemProcesses:
    """Test behavior with system processes."""

    def test_system_processes(self, psutil_module):
        """Test behavior with system processes - Cygwin compatible version."""
        all_pids = psutil_module.pids()
        assert len(all_pids) > 0, "No PIDs found at all"

        # Test some existing PIDs (use first few from the list)
        test_pid_count = 0
        test_pids = all_pids[: min(10, len(all_pids))]

        for pid in test_pids:
            if psutil_module.pid_exists(pid):
                test_pid_count += 1
                # If exists, should be in pids() list
                current_pids = psutil_module.pids()
                assert (
                    pid in current_pids
                ), f"PID {pid} exists but not in pids() list"

        # Should have at least some working PIDs
        assert test_pid_count > 0, "No working PIDs found"

        # Test that our own PID and parent PID work (should always be true)
        own_pid = os.getpid()
        parent_pid = os.getppid()

        assert psutil_module.pid_exists(own_pid), "Own PID should exist"
        assert psutil_module.pid_exists(parent_pid), "Parent PID should exist"
        assert own_pid in all_pids, "Own PID should be in pids() list"
        assert parent_pid in all_pids, "Parent PID should be in pids() list"

    def test_process_enumeration_completeness(self, psutil_module):
        """Test that process enumeration finds a reasonable number of
        processes.
        """
        pids = psutil_module.pids()

        # Should find a reasonable number of processes (at least 10 on most
        # systems)
        assert len(pids) >= 3, f"Too few processes found: {len(pids)}"

        # Should not find an unreasonable number of processes
        assert len(pids) <= 50000, f"Too many processes found: {len(pids)}"

        # All PIDs should be valid integers
        for pid in pids:
            assert isinstance(pid, int), f"Non-integer PID: {pid}"
            assert 0 < pid < 2**31, f"PID out of reasonable range: {pid}"
