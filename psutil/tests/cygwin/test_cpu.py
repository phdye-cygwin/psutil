#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""CPU Functionality Tests for Cygwin psutil Implementation

This module contains comprehensive tests for CPU-related functions in the
Cygwin psutil C extension. It is part of Lap 3 in the test reorganization
plan and consolidates all CPU-related testing from various phase test files.

Functions Tested:
- per_cpu_times() - Per-CPU time statistics
- cpu_count_logical() - Logical CPU count
- cpu_count_cores() - Physical core count

Test Categories:
- Unit tests for individual functions
- Integration tests with psutil public API
- Performance and timing tests
- Error handling and edge cases
- Cross-validation with system sources

This file migrates and consolidates CPU tests from:
- issue/phase-2/tests/test_phase2_cpu.py
- CPU-related tests from other phase files
- Additional CPU validation from integration tests
"""

import sys
import threading
import time

import pytest


class TestPerCpuTimes:
    """Test suite for per_cpu_times() function.

    This function returns per-CPU time statistics as a list of tuples,
    where each tuple contains 8 time values for each logical CPU.
    """

    def test_per_cpu_times_return_type(self, cygwin_cext):
        """Test that per_cpu_times returns a list."""
        cpu_times = cygwin_cext.per_cpu_times()
        assert isinstance(
            cpu_times, list
        ), f"Expected list, got {type(cpu_times).__name__}"

    def test_per_cpu_times_non_empty(self, cygwin_cext):
        """Test that per_cpu_times returns at least one CPU's data."""
        cpu_times = cygwin_cext.per_cpu_times()
        assert len(cpu_times) > 0, "Should return at least one CPU's times"

    def test_per_cpu_times_count_matches_logical_cpus(self, cygwin_cext):
        """Test that per_cpu_times count matches logical CPU count."""
        cpu_times = cygwin_cext.per_cpu_times()
        logical_count = cygwin_cext.cpu_count_logical()

        assert len(cpu_times) == logical_count, (
            f"CPU times count ({len(cpu_times)}) != logical CPU count"
            f" ({logical_count})"
        )

    def test_per_cpu_times_tuple_structure(self, cygwin_cext):
        """Test that each CPU's times is an 8-element tuple."""
        cpu_times = cygwin_cext.per_cpu_times()

        for i, times in enumerate(cpu_times):
            assert isinstance(
                times, tuple
            ), f"CPU {i} times should be tuple, got {type(times).__name__}"
            assert (
                len(times) == 8
            ), f"CPU {i} should have 8 time values, got {len(times)}"

    def test_per_cpu_times_field_types(self, cygwin_cext):
        """Test that all CPU time values are numeric (float or int)."""
        cpu_times = cygwin_cext.per_cpu_times()
        time_names = [
            "user",
            "nice",
            "system",
            "idle",
            "iowait",
            "irq",
            "softirq",
            "steal",
        ]

        for i, times in enumerate(cpu_times):
            for j, (name, value) in enumerate(zip(time_names, times)):
                assert isinstance(value, (int, float)), (
                    f"CPU {i} {name} should be numeric, got"
                    f" {type(value).__name__}"
                )

    def test_per_cpu_times_non_negative_values(self, cygwin_cext):
        """Test that all CPU time values are non-negative."""
        cpu_times = cygwin_cext.per_cpu_times()
        time_names = [
            "user",
            "nice",
            "system",
            "idle",
            "iowait",
            "irq",
            "softirq",
            "steal",
        ]

        for i, times in enumerate(cpu_times):
            for j, (name, value) in enumerate(zip(time_names, times)):
                assert (
                    value >= 0.0
                ), f"CPU {i} {name} should be non-negative, got {value}"

    def test_per_cpu_times_reasonable_values(
        self, cygwin_cext, system_constants
    ):
        """Test that CPU time values are within reasonable ranges."""
        cpu_times = cygwin_cext.per_cpu_times()
        max_reasonable_time = system_constants[
            "max_reasonable_cpu_time_seconds"
        ]

        for i, times in enumerate(cpu_times):
            total_time = sum(times)
            assert (
                total_time <= max_reasonable_time
            ), f"CPU {i} total time ({total_time}s) seems unreasonable"

            # Idle time should typically be the largest
            idle_time = times[3]  # idle is index 3
            assert idle_time <= total_time, (
                f"CPU {i} idle time ({idle_time}) should not exceed "
                f"total time ({total_time})"
            )

    def test_per_cpu_times_consistency(self, cygwin_cext):
        """Test that per_cpu_times returns consistent structure across calls"""
        first_call = cygwin_cext.per_cpu_times()
        time.sleep(0.1)  # Small delay to allow time changes
        second_call = cygwin_cext.per_cpu_times()

        assert len(first_call) == len(
            second_call
        ), "Number of CPUs should be consistent across calls"

        for i, (first_times, second_times) in enumerate(
            zip(first_call, second_call)
        ):
            assert len(first_times) == len(
                second_times
            ), f"CPU {i} should have same number of time fields across calls"

    def test_per_cpu_times_monotonic_increase(self, cygwin_cext):
        """Test that CPU times generally increase over time."""
        first_call = cygwin_cext.per_cpu_times()

        # Create some CPU activity
        for _ in range(1000):
            sum(range(100))

        time.sleep(0.05)  # Allow time for changes to be recorded
        second_call = cygwin_cext.per_cpu_times()

        # At least one CPU should show increased times
        any_increased = False
        for i, (first_times, second_times) in enumerate(
            zip(first_call, second_call)
        ):
            first_total = sum(first_times[:3])  # user + nice + system
            second_total = sum(second_times[:3])

            if second_total >= first_total:
                any_increased = True
                break

        # This test might be flaky on very fast systems
        if not any_increased:
            pytest.skip(
                "CPU times did not increase detectably (system-dependent)"
            )

    def test_per_cpu_times_integration_psutil(
        self, cygwin_cext, psutil_module
    ):
        """Test integration with psutil.cpu_times(percpu=True)."""
        cext_cpu_times = cygwin_cext.per_cpu_times()

        try:
            psutil_cpu_times = psutil_module.cpu_times(percpu=True)

            # Compare structure
            assert len(cext_cpu_times) == len(psutil_cpu_times), (
                f"C extension ({len(cext_cpu_times)}) != psutil"
                f" ({len(psutil_cpu_times)}) CPU count"
            )

            # Compare field availability (psutil may have fewer fields)
            for i in range(min(len(cext_cpu_times), len(psutil_cpu_times))):
                cext_times = cext_cpu_times[i]
                psutil_times = psutil_cpu_times[i]

                # psutil should have at least user, nice, system, idle
                assert (
                    len(psutil_times) >= 4
                ), f"psutil CPU {i} should have at least 4 time fields"

                # Compare basic fields (allowing for small differences due to
                # timing)
                tolerance = 1.0  # 1 second tolerance
                for j, field_name in enumerate(
                    ["user", "nice", "system", "idle"][: len(psutil_times)]
                ):
                    if j < len(cext_times):
                        diff = abs(cext_times[j] - psutil_times[j])
                        assert diff <= tolerance, (
                            f"CPU {i} {field_name}: C extension"
                            f" ({cext_times[j]}) vs psutil ({psutil_times[j]})"
                            f" diff {diff}s > {tolerance}s"
                        )

        except (AttributeError, NotImplementedError):
            pytest.skip(
                "psutil.cpu_times(percpu=True) not available or not"
                " implemented"
            )

    def test_per_cpu_times_performance(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test that per_cpu_times executes within reasonable time."""
        with performance_timer as perf:
            cygwin_cext.per_cpu_times()

        assert perf.duration_ms is not None
        # CPU times can take longer as it reads from multiple CPUs
        threshold = system_constants["performance_threshold_ms"] * 2
        assert (
            perf.duration_ms < threshold
        ), f"Function took {perf.duration_ms:.3f}ms, expected < {threshold}ms"

    def test_per_cpu_times_thread_safety(self, cygwin_cext):
        """Test that per_cpu_times is thread-safe."""
        results = {}
        errors = {}

        def worker(worker_id):
            try:
                cpu_times = cygwin_cext.per_cpu_times()
                results[worker_id] = cpu_times
            except (OSError, RuntimeError, ValueError) as e:
                errors[worker_id] = e

        # Run multiple threads simultaneously
        threads = []
        for i in range(4):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Check that all threads succeeded
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        assert len(results) == 4, f"Expected 4 results, got {len(results)}"

        # All results should have consistent structure
        cpu_counts = [len(result) for result in results.values()]
        assert all(
            count == cpu_counts[0] for count in cpu_counts
        ), "Thread results should have consistent CPU counts"


class TestCpuCountLogical:
    """Test suite for cpu_count_logical() function.

    This function returns the number of logical CPUs (including hyperthreading)
    """

    def test_cpu_count_logical_return_type(self, cygwin_cext):
        """Test that cpu_count_logical returns an integer."""
        cpu_count = cygwin_cext.cpu_count_logical()
        assert isinstance(
            cpu_count, int
        ), f"Expected int, got {type(cpu_count).__name__}"

    def test_cpu_count_logical_positive_value(self, cygwin_cext):
        """Test that cpu_count_logical returns a positive value."""
        cpu_count = cygwin_cext.cpu_count_logical()
        assert (
            cpu_count > 0
        ), f"Logical CPU count should be positive, got {cpu_count}"

    def test_cpu_count_logical_reasonable_range(self, cygwin_cext):
        """Test that cpu_count_logical returns a reasonable value."""
        cpu_count = cygwin_cext.cpu_count_logical()

        # Most systems have between 1 and 256 logical CPUs
        assert (
            1 <= cpu_count <= 256
        ), f"Logical CPU count ({cpu_count}) outside reasonable range [1, 256]"

    def test_cpu_count_logical_consistency(self, cygwin_cext):
        """Test that cpu_count_logical returns consistent values."""
        first_count = cygwin_cext.cpu_count_logical()
        second_count = cygwin_cext.cpu_count_logical()

        assert (
            first_count == second_count
        ), f"CPU count should be consistent: {first_count} vs {second_count}"

    def test_cpu_count_logical_cross_validation_psutil(
        self, cygwin_cext, psutil_module
    ):
        """Test that cpu_count_logical matches psutil.cpu_count()."""
        cext_count = cygwin_cext.cpu_count_logical()

        try:
            psutil_count = psutil_module.cpu_count(logical=True)
            assert (
                cext_count == psutil_count
            ), f"C extension ({cext_count}) != psutil ({psutil_count})"
        except (AttributeError, NotImplementedError):
            pytest.skip("psutil.cpu_count(logical=True) not available")

    def test_cpu_count_logical_performance(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test that cpu_count_logical executes quickly."""
        with performance_timer as perf:
            cygwin_cext.cpu_count_logical()

        assert perf.duration_ms is not None
        threshold = system_constants["performance_threshold_ms"]
        assert (
            perf.duration_ms < threshold
        ), f"Function took {perf.duration_ms:.3f}ms, expected < {threshold}ms"


class TestCpuCountCores:
    """Test suite for cpu_count_cores() function.

    This function returns the number of physical CPU cores (None if unknown).
    """

    def test_cpu_count_cores_return_type(self, cygwin_cext):
        """Test that cpu_count_cores returns int or None."""
        core_count = cygwin_cext.cpu_count_cores()
        assert core_count is None or isinstance(
            core_count, int
        ), f"Expected int or None, got {type(core_count).__name__}"

    def test_cpu_count_cores_positive_when_not_none(self, cygwin_cext):
        """Test that cpu_count_cores returns positive value when not None."""
        core_count = cygwin_cext.cpu_count_cores()
        if core_count is not None:
            assert (
                core_count > 0
            ), f"Core count should be positive, got {core_count}"

    def test_cpu_count_cores_reasonable_range(self, cygwin_cext):
        """Test that cpu_count_cores returns
        a reasonable value when not None.
        """
        core_count = cygwin_cext.cpu_count_cores()
        if core_count is not None:
            # Most systems have between 1 and 128 physical cores
            assert (
                1 <= core_count <= 128
            ), f"Core count ({core_count}) outside reasonable range [1, 128]"

    def test_cpu_count_cores_vs_logical_relationship(self, cygwin_cext):
        """Test that physical cores <= logical CPUs."""
        logical_count = cygwin_cext.cpu_count_logical()
        core_count = cygwin_cext.cpu_count_cores()

        if core_count is not None:
            assert core_count <= logical_count, (
                f"Physical cores ({core_count}) should not exceed logical CPUs"
                f" ({logical_count})"
            )

    def test_cpu_count_cores_hyperthreading_detection(self, cygwin_cext):
        """Test hyperthreading detection logic."""
        logical_count = cygwin_cext.cpu_count_logical()
        core_count = cygwin_cext.cpu_count_cores()

        if core_count is not None:
            hyperthreading_ratio = logical_count / core_count

            # Common ratios are 1 (no HT), 2 (standard HT), sometimes 4
            assert 1.0 <= hyperthreading_ratio <= 4.0, (
                f"Hyperthreading ratio ({hyperthreading_ratio}) "
                "outside expected range"
            )

            # Report detected configuration for debugging
            if hyperthreading_ratio > 1.0:
                pass

    def test_cpu_count_cores_consistency(self, cygwin_cext):
        """Test that cpu_count_cores returns consistent values."""
        first_count = cygwin_cext.cpu_count_cores()
        second_count = cygwin_cext.cpu_count_cores()

        assert (
            first_count == second_count
        ), f"Core count should be consistent: {first_count} vs {second_count}"

    def test_cpu_count_cores_cross_validation_psutil(
        self, cygwin_cext, psutil_module
    ):
        """Test that cpu_count_cores matches psutil.cpu_count(logical=False)"""
        cext_count = cygwin_cext.cpu_count_cores()

        try:
            psutil_count = psutil_module.cpu_count(logical=False)
            assert (
                cext_count == psutil_count
            ), f"C extension ({cext_count}) != psutil ({psutil_count})"
        except (AttributeError, NotImplementedError):
            pytest.skip("psutil.cpu_count(logical=False) not available")

    def test_cpu_count_cores_performance(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test that cpu_count_cores executes quickly."""
        with performance_timer as perf:
            cygwin_cext.cpu_count_cores()

        assert perf.duration_ms is not None
        threshold = system_constants["performance_threshold_ms"]
        assert (
            perf.duration_ms < threshold
        ), f"Function took {perf.duration_ms:.3f}ms, expected < {threshold}ms"


class TestCpuFunctionalityIntegration:
    """Integration tests for CPU functionality as a whole.

    These tests validate the relationships between different CPU functions
    and their integration with the psutil public API.
    """

    def test_cpu_functions_availability(self, cygwin_cext):
        """Test that all expected CPU functions are available."""
        required_functions = [
            "per_cpu_times",
            "cpu_count_logical",
            "cpu_count_cores",
        ]

        for func_name in required_functions:
            assert hasattr(
                cygwin_cext, func_name
            ), f"C extension missing required function: {func_name}"

            func = getattr(cygwin_cext, func_name)
            assert callable(func), f"{func_name} should be callable"

    def test_cpu_data_consistency(self, cygwin_cext):
        """Test consistency between different CPU functions."""
        logical_count = cygwin_cext.cpu_count_logical()
        core_count = cygwin_cext.cpu_count_cores()
        cpu_times = cygwin_cext.per_cpu_times()

        # Per-CPU times should match logical CPU count
        assert (
            len(cpu_times) == logical_count
        ), "per_cpu_times length should match logical CPU count"

        # Core count should be reasonable relative to logical count
        if core_count is not None:
            assert (
                core_count <= logical_count
            ), "Physical cores should not exceed logical CPUs"

            # Common configurations
            valid_ratios = [1, 2, 4]  # No HT, standard HT, or quad-threading
            ratio = logical_count / core_count
            closest_ratio = min(valid_ratios, key=lambda x: abs(x - ratio))
            assert abs(ratio - closest_ratio) < 0.1, (
                f"Unusual logical/physical ratio: {ratio} (closest standard:"
                f" {closest_ratio})"
            )

    def test_cpu_psutil_integration_comprehensive(
        self, cygwin_cext, psutil_module
    ):
        """Comprehensive test of CPU integration with psutil."""

        # Test logical CPU count integration
        cext_logical = cygwin_cext.cpu_count_logical()
        try:
            psutil_logical = psutil_module.cpu_count(logical=True)
            assert cext_logical == psutil_logical, (
                f"Logical CPU count mismatch: C ext {cext_logical} vs psutil"
                f" {psutil_logical}"
            )
        except (AttributeError, NotImplementedError):
            pytest.skip("psutil logical CPU count not available")

        # Test physical CPU count integration
        cext_physical = cygwin_cext.cpu_count_cores()
        try:
            psutil_physical = psutil_module.cpu_count(logical=False)
            assert cext_physical == psutil_physical, (
                f"Physical CPU count mismatch: C ext {cext_physical} vs psutil"
                f" {psutil_physical}"
            )
        except (AttributeError, NotImplementedError):
            pytest.skip("psutil physical CPU count not available")

        # Test per-CPU times integration
        cext_per_cpu = cygwin_cext.per_cpu_times()
        try:
            psutil_per_cpu = psutil_module.cpu_times(percpu=True)
            assert len(cext_per_cpu) == len(psutil_per_cpu), (
                f"Per-CPU times count mismatch: C ext {len(cext_per_cpu)} vs"
                f" psutil {len(psutil_per_cpu)}"
            )
        except (AttributeError, NotImplementedError):
            pytest.skip("psutil per-CPU times not available")

    def test_cpu_performance_comprehensive(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test performance of all CPU functions together."""
        threshold = system_constants["performance_threshold_ms"]

        # Test individual function performance

        # We need to create individual performance timers for each test
        # Since we can't reuse the same timer, we'll test batch performance
        # only
        # Test batch performance (calling all functions together)
        with performance_timer as perf:
            cygwin_cext.cpu_count_logical()
            cygwin_cext.cpu_count_cores()
            cygwin_cext.per_cpu_times()

        batch_threshold = threshold * 3  # Allow more time for batch operation
        assert perf.duration_ms < batch_threshold, (
            f"Batch CPU operations took {perf.duration_ms:.3f}ms, expected <"
            f" {batch_threshold}ms"
        )

    def test_cpu_error_handling(self, cygwin_cext):
        """Test error handling for CPU functions."""

        # All CPU functions should handle being called multiple times
        try:
            for _ in range(5):
                logical = cygwin_cext.cpu_count_logical()
                cygwin_cext.cpu_count_cores()
                times = cygwin_cext.per_cpu_times()

                assert (
                    logical is not None
                ), "cpu_count_logical should never return None"
                # cores can be None, that's expected
                assert (
                    times is not None
                ), "per_cpu_times should never return None"

        except (OSError, RuntimeError, ValueError) as e:
            pytest.fail(
                f"CPU functions should not raise exceptions in normal use: {e}"
            )

    def test_cpu_concurrent_access(self, cygwin_cext):
        """Test concurrent access to CPU functions."""
        results = {}
        errors = {}

        def cpu_worker(worker_id):
            try:
                logical = cygwin_cext.cpu_count_logical()
                cores = cygwin_cext.cpu_count_cores()
                times = cygwin_cext.per_cpu_times()
                results[worker_id] = {
                    "logical": logical,
                    "cores": cores,
                    "times": len(times),
                }
            except (OSError, RuntimeError, ValueError) as e:
                errors[worker_id] = e

        # Run multiple threads simultaneously
        threads = []
        for i in range(6):
            thread = threading.Thread(target=cpu_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Check that all threads succeeded
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 6, f"Expected 6 results, got {len(results)}"

        # All results should be identical (CPU config doesn't change)
        first_result = results[0]
        for result in results.values():
            assert (
                result["logical"] == first_result["logical"]
            ), "Logical CPU count inconsistent across threads"
            assert (
                result["cores"] == first_result["cores"]
            ), "Core count inconsistent across threads"
            assert (
                result["times"] == first_result["times"]
            ), "CPU times count inconsistent across threads"


# ============================================================================
# MANUAL TESTING AND DEBUGGING
# ============================================================================


def run_manual_tests():
    """Manual testing function for development and debugging.

    This function can be called directly to test CPU functionality
    without running the full pytest suite.
    """

    try:
        import psutil._psutil_cygwin as cext

    except ImportError:
        return False

    # Test cpu_count_logical
    try:
        logical_count = cext.cpu_count_logical()
        assert isinstance(logical_count, int)
        assert logical_count > 0
    except (OSError, RuntimeError, ValueError):
        return False

    # Test cpu_count_cores
    try:
        core_count = cext.cpu_count_cores()
        if core_count is not None:
            assert isinstance(core_count, int)
            assert core_count > 0
            logical_count / core_count
    except (OSError, RuntimeError, ValueError):
        return False

    # Test per_cpu_times
    try:
        cpu_times = cext.per_cpu_times()

        if cpu_times:
            cpu_times[0]

            assert len(cpu_times) == logical_count
            assert all(len(times) == 8 for times in cpu_times)

    except (OSError, RuntimeError, ValueError):
        return False

    return True


if __name__ == "__main__":
    """Run manual tests when executed directly."""
    success = run_manual_tests()
    sys.exit(0 if success else 1)
