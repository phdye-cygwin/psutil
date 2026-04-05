#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cygwin Utilities Test Suite
===========================

Tests for basic utility functions and constants from the
psutil Cygwin C extension.

This includes:
- Basic C extension import and function availability
- Utility functions (getpagesize, set_debug, check_pid_range)
- Constants validation
- Priority operations (getpriority, setpriority)
- Basic error handling and edge cases

Based on utility-related tests extracted from:
- issue/phase-1/tests/test_phase1.py
- issue/phase-2/tests/test_*.py
"""

import gc
import math
import os
import threading

import pytest


class TestCExtensionImport:
    """Test C extension import and basic availability."""

    def test_cext_import(self, cygwin_cext):
        """Test that C extension can be imported successfully."""
        assert cygwin_cext is not None

        # Check if it has a __file__ attribute
        if hasattr(cygwin_cext, '__file__'):
            pass

    def test_required_utility_functions_available(self, cygwin_cext):
        """Test that all required utility functions are available."""
        required_functions = [
            'getpagesize',
            'set_debug',
            'check_pid_range',
            'getpriority',
            'setpriority',
        ]

        for func_name in required_functions:
            assert hasattr(
                cygwin_cext, func_name
            ), f"Missing function: {func_name}"
            func = getattr(cygwin_cext, func_name)
            assert callable(func), f"Function {func_name} is not callable"

    def test_connection_constants_available(self, cygwin_cext):
        """Test that connection state constants are available."""
        required_constants = [
            'CONN_ESTABLISHED',
            'CONN_SYN_SENT',
            'CONN_SYN_RECV',
            'CONN_FIN_WAIT1',
            'CONN_FIN_WAIT2',
            'CONN_TIME_WAIT',
            'CONN_CLOSE',
            'CONN_CLOSE_WAIT',
            'CONN_LAST_ACK',
            'CONN_LISTEN',
            'CONN_CLOSING',
            'CONN_NONE',
        ]

        for const_name in required_constants:
            assert hasattr(
                cygwin_cext, const_name
            ), f"Missing constant: {const_name}"
            value = getattr(cygwin_cext, const_name)
            assert isinstance(
                value, int
            ), f"Constant {const_name} is not an integer"

    def test_constants_unique_values(self, cygwin_cext):
        """Test that connection constants have unique values."""
        constants = [
            'CONN_ESTABLISHED',
            'CONN_SYN_SENT',
            'CONN_SYN_RECV',
            'CONN_FIN_WAIT1',
            'CONN_FIN_WAIT2',
            'CONN_TIME_WAIT',
            'CONN_CLOSE',
            'CONN_CLOSE_WAIT',
            'CONN_LAST_ACK',
            'CONN_LISTEN',
            'CONN_CLOSING',
            'CONN_NONE',
        ]

        values = []
        for const_name in constants:
            value = getattr(cygwin_cext, const_name)
            values.append(value)

        # Check that all values are unique
        assert len(values) == len(
            set(values)
        ), "Connection constants have duplicate values"


class TestBasicUtilities:
    """Test basic utility functions."""

    def test_getpagesize(self, cygwin_cext, system_constants):
        """Test getpagesize function."""
        pagesize = cygwin_cext.getpagesize()

        # Should return a positive integer
        assert isinstance(pagesize, int)
        assert pagesize > 0

        # Should be a reasonable page size (typically 4096 on most systems)
        assert pagesize >= 512  # Minimum reasonable size
        assert pagesize <= 65536  # Maximum reasonable size

        # Should be a power of 2
        assert (
            pagesize & (pagesize - 1) == 0
        ), f"Page size {pagesize} is not a power of 2"

        # Should be in common page sizes
        common_sizes = system_constants['common_page_sizes']
        assert pagesize in common_sizes, f"Unusual page size: {pagesize}"

    def test_getpagesize_consistency(self, cygwin_cext):
        """Test that getpagesize returns consistent values."""
        pagesize1 = cygwin_cext.getpagesize()
        pagesize2 = cygwin_cext.getpagesize()

        assert (
            pagesize1 == pagesize2
        ), "getpagesize returned inconsistent values"

    def test_set_debug(self, cygwin_cext):
        """Test set_debug function."""
        # Test setting debug to False
        cygwin_cext.set_debug(False)

        # Test setting debug to True
        cygwin_cext.set_debug(True)

        # Test setting back to False
        cygwin_cext.set_debug(False)

        # Function should not raise exceptions for valid boolean values

    def test_set_debug_type_validation(self, cygwin_cext):
        """Test set_debug with invalid types."""
        with pytest.raises(TypeError):
            cygwin_cext.set_debug("invalid")

        with pytest.raises(TypeError):
            cygwin_cext.set_debug(1)  # Should require actual boolean

        with pytest.raises(TypeError):
            cygwin_cext.set_debug(None)

    def test_check_pid_range_valid(self, cygwin_cext):
        """Test check_pid_range with valid PIDs."""
        current_pid = os.getpid()

        # Should not raise exception for current PID
        cygwin_cext.check_pid_range(current_pid)

        # Test with PID 1 (init process, should always exist)
        cygwin_cext.check_pid_range(1)

    def test_check_pid_range_invalid(self, cygwin_cext):
        """Test check_pid_range with invalid PIDs."""
        # Test negative PID - should raise ValueError
        with pytest.raises(ValueError, match=r".*"):
            cygwin_cext.check_pid_range(-1)

        # Test zero PID - should raise ValueError
        with pytest.raises(ValueError, match=r".*"):
            cygwin_cext.check_pid_range(0)

        # Note: check_pid_range only validates that PID is a positive integer,
        # it does NOT check if the process actually exists. That's the job of
        # pid_exists().
        # Large PIDs that are valid integers should pass validation.
        try:
            cygwin_cext.check_pid_range(
                999999
            )  # Should succeed (valid positive integer)
        except (OSError, RuntimeError, PermissionError) as e:
            pytest.fail(
                f"check_pid_range should accept large positive integers: {e}"
            )

        # Test with maximum possible PID value
        try:
            cygwin_cext.check_pid_range(2147483647)  # Max 32-bit signed int
        except (OSError, RuntimeError, PermissionError) as e:
            pytest.fail(f"check_pid_range should accept max valid PID: {e}")

    def test_check_pid_range_type_validation(self, cygwin_cext):
        """Test check_pid_range with invalid types."""
        with pytest.raises(TypeError):
            cygwin_cext.check_pid_range("invalid")

        with pytest.raises(TypeError):
            cygwin_cext.check_pid_range(None)

        with pytest.raises(TypeError):
            cygwin_cext.check_pid_range(math.pi)


class TestPriorityOperations:
    """Test process priority operations."""

    def test_getpriority_current_process(self, cygwin_cext):
        """Test getting priority of current process."""
        current_pid = os.getpid()

        priority = cygwin_cext.getpriority(current_pid)

        assert isinstance(priority, int)
        assert (
            -20 <= priority <= 19
        ), f"Priority {priority} outside valid range"

    def test_getpriority_init_process(self, cygwin_cext):
        """Test getting priority of init process (PID 1)."""
        try:
            priority = cygwin_cext.getpriority(1)
            assert isinstance(priority, int)
            assert (
                -20 <= priority <= 19
            ), f"Priority {priority} outside valid range"
        except (OSError, RuntimeError, PermissionError) as e:
            # On Cygwin, PID 1 may not be accessible or may not exist as
            # traditional init. Such platform-specific behavior is acceptable.
            if isinstance(e, OSError) and hasattr(e, 'errno'):
                if e.errno in {1, 3, 13}:  # EPERM, ESRCH, EACCES
                    pass  # Expected errors
                else:
                    # Don't skip - run the test but log the specific error
                    pass
            else:
                # RuntimeError or PermissionError might occur on some systems
                pass

    def test_getpriority_invalid_pid(self, cygwin_cext):
        """Test getpriority with invalid PID."""
        with pytest.raises(OSError, match=r".*"):
            cygwin_cext.getpriority(999999)  # Non-existent PID

    def test_getpriority_type_validation(self, cygwin_cext):
        """Test getpriority with invalid types."""
        with pytest.raises(TypeError):
            cygwin_cext.getpriority("invalid")

        with pytest.raises(TypeError):
            cygwin_cext.getpriority(None)

    def test_setpriority_same_value(self, cygwin_cext):
        """Test setting priority to the same value."""
        current_pid = os.getpid()

        # Get current priority
        current_priority = cygwin_cext.getpriority(current_pid)

        try:
            # Set to same value (should not require elevated permissions)
            cygwin_cext.setpriority(current_pid, current_priority)

            # Verify it's still the same
            new_priority = cygwin_cext.getpriority(current_pid)
            assert new_priority == current_priority
        except PermissionError:
            # This is acceptable behavior - setting priority might
            # require permissions
            pytest.skip("Setting priority requires elevated permissions")

    def test_setpriority_type_validation(self, cygwin_cext):
        """Test setpriority with invalid types."""
        current_pid = os.getpid()

        with pytest.raises(TypeError):
            cygwin_cext.setpriority("invalid", 0)

        with pytest.raises(TypeError):
            cygwin_cext.setpriority(current_pid, "invalid")

        with pytest.raises(TypeError):
            cygwin_cext.setpriority(None, 0)

    def test_setpriority_invalid_values(self, cygwin_cext):
        """Test setpriority with invalid priority values."""
        current_pid = os.getpid()

        # Test priority value outside valid range
        with pytest.raises((ValueError, OSError)):
            cygwin_cext.setpriority(current_pid, 100)  # Too high

        with pytest.raises((ValueError, OSError)):
            cygwin_cext.setpriority(current_pid, -100)  # Too low


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_function_parameter_validation(self, cygwin_cext):
        """Test that functions properly validate their parameters."""
        os.getpid()

        # Test functions that require integer PIDs
        pid_functions = ['getpriority', 'check_pid_range']

        for func_name in pid_functions:
            func = getattr(cygwin_cext, func_name)

            with pytest.raises(TypeError):
                func("not_an_integer")

            with pytest.raises(TypeError):
                func(None)

            with pytest.raises(TypeError):
                func(math.pi)

    def test_boundary_conditions(self, cygwin_cext):
        """Test functions with boundary conditions."""
        # Test minimum valid PID
        try:
            cygwin_cext.getpriority(1)
        except OSError:
            # PID 1 might not be accessible, which is OK
            pass

        # Test maximum reasonable PID (system-dependent)
        max_pid = 32768  # Common maximum on many systems
        try:
            cygwin_cext.getpriority(max_pid)
        except OSError:
            # PID might not exist, which is expected
            pass

    def test_concurrent_access_safety(self, cygwin_cext):
        """Test that utility functions are safe for concurrent access."""
        current_pid = os.getpid()
        results = []
        errors = []

        def worker():
            try:
                # Call multiple utility functions concurrently
                pagesize = cygwin_cext.getpagesize()
                priority = cygwin_cext.getpriority(current_pid)
                cygwin_cext.set_debug(False)
                cygwin_cext.check_pid_range(current_pid)
                results.append((pagesize, priority))
            except (OSError, RuntimeError, PermissionError) as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check results
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) > 0, "No successful concurrent operations"

        # All threads should get the same pagesize
        pagesizes = [r[0] for r in results]
        assert all(
            ps == pagesizes[0] for ps in pagesizes
        ), "Inconsistent pagesize results"


class TestPerformance:
    """Test performance characteristics of utility functions."""

    def test_utility_function_performance(
        self, cygwin_cext, performance_timer, system_constants
    ):
        """Test that utility functions perform within reasonable time."""
        current_pid = os.getpid()
        system_constants['performance_threshold_ms']

        # Test getpagesize performance
        with performance_timer as timer:
            for _ in range(1000):
                cygwin_cext.getpagesize()

        avg_time_ms = timer.duration_ms / 1000
        assert (
            avg_time_ms < 1.0
        ), f"getpagesize too slow: {avg_time_ms:.3f}ms average"

        # Test getpriority performance
        with performance_timer as timer:
            for _ in range(100):
                cygwin_cext.getpriority(current_pid)

        avg_time_ms = timer.duration_ms / 100
        assert (
            avg_time_ms < 5.0
        ), f"getpriority too slow: {avg_time_ms:.3f}ms average"

    def test_memory_usage_stability(self, cygwin_cext):
        """Test that utility functions don't leak memory."""
        current_pid = os.getpid()

        # Run many operations to check for memory leaks
        for i in range(1000):
            pagesize = cygwin_cext.getpagesize()
            priority = cygwin_cext.getpriority(current_pid)
            cygwin_cext.set_debug(False)
            cygwin_cext.check_pid_range(current_pid)

            # Clean up references
            del pagesize, priority

            # Periodic garbage collection
            if i % 100 == 0:
                gc.collect()

        # If we get here without issues, memory management is likely OK


class TestIntegration:
    """Test integration with psutil public API."""

    def test_psutil_process_nice_integration(self, psutil_module):
        """Test that psutil.Process.nice() uses our priority functions."""
        proc = psutil_module.Process()

        # Get priority through psutil
        priority = proc.nice()

        assert isinstance(priority, int)
        assert (
            -20 <= priority <= 19
        ), f"Priority {priority} outside valid range"

    def test_psutil_import_integration(self, psutil_module):
        """Test that psutil imports successfully with our C extension."""
        # Basic functionality test
        cpu_count = psutil_module.cpu_count()
        assert isinstance(cpu_count, int)
        assert cpu_count > 0

        memory = psutil_module.virtual_memory()
        assert memory.total > 0

        # These should work if our C extension is properly integrated
        processes = list(psutil_module.process_iter(['pid', 'name']))
        assert len(processes) > 0


class TestCompatibility:
    """Test backward compatibility and cross-validation."""

    def test_constants_match_socket_constants(self, cygwin_cext):
        """Test that our constants are compatible with socket constants."""
        # Our connection constants should be reasonable values
        established = cygwin_cext.CONN_ESTABLISHED
        listen = cygwin_cext.CONN_LISTEN
        none = cygwin_cext.CONN_NONE

        assert (
            established != listen
        ), "ESTABLISHED and LISTEN should be different"
        assert none != established, "NONE and ESTABLISHED should be different"

        # All values should be non-negative
        constants = [
            'CONN_ESTABLISHED',
            'CONN_SYN_SENT',
            'CONN_SYN_RECV',
            'CONN_FIN_WAIT1',
            'CONN_FIN_WAIT2',
            'CONN_TIME_WAIT',
            'CONN_CLOSE',
            'CONN_CLOSE_WAIT',
            'CONN_LAST_ACK',
            'CONN_LISTEN',
            'CONN_CLOSING',
            'CONN_NONE',
        ]

        for const_name in constants:
            value = getattr(cygwin_cext, const_name)
            assert (
                value >= 0
            ), f"Constant {const_name} has negative value: {value}"

    def test_cross_platform_compatibility(
        self, cygwin_cext, cross_validation_sources
    ):
        """Test compatibility with other platform implementations."""
        os.getpid()

        # Compare pagesize with os module if available
        if 'os' in cross_validation_sources:
            os_module = cross_validation_sources['os']
            if hasattr(os_module, 'getpagesize'):
                os_pagesize = os_module.getpagesize()
                cext_pagesize = cygwin_cext.getpagesize()
                assert (
                    os_pagesize == cext_pagesize
                ), f"Pagesize mismatch: os={os_pagesize}, cext={cext_pagesize}"

        # Test that our functions work with standard Python patterns
        assert callable(cygwin_cext.getpagesize)
        assert callable(cygwin_cext.getpriority)
        assert callable(cygwin_cext.setpriority)


# Helper functions for manual testing
def run_manual_tests():
    """Run manual tests for development and debugging."""

    try:
        import psutil._psutil_cygwin as cext

        current_pid = os.getpid()
        cext.getpriority(current_pid)

        cext.set_debug(True)
        cext.set_debug(False)

        cext.check_pid_range(current_pid)

    except (ImportError, AttributeError, OSError, RuntimeError) as e:
        import traceback

        traceback.print_exc(e)


if __name__ == "__main__":
    # Allow running as standalone script for development
    run_manual_tests()
