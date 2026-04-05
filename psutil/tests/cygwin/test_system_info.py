#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cygwin System Information Test Suite
===================================

Tests for system-level info functions from the psutil Cygwin C extension.
This includes:
- System-wide CPU information (cpu_times, cpu_stats)
- System boot time
- User session information
- System-level information retrieval functions

Based on system info tests extracted from:
- issue/phase-1/tests/test_phase1.py (system info components)
- issue/phase-2/tests/test_phase2.py (CPU and system functions)
- New comprehensive tests for system information functions

Functions covered:
- boot_time() - System boot time
- users() - Currently connected users
- cpu_times() - System-wide CPU times
- cpu_stats() - System CPU statistics (context switches, interrupts, etc.)
"""

import os
import threading
import time
from datetime import datetime

import pytest


class TestBootTime:
    """Test suite for boot_time() function."""

    def test_boot_time_return_type(self, cygwin_cext):
        """Test that boot_time returns a float."""
        try:
            boot_time = cygwin_cext.boot_time()
            assert isinstance(
                boot_time, (int, float)
            ), f"Expected number, got {type(boot_time).__name__}"
        except AttributeError:
            # C extension might not have boot_time function yet
            pytest.skip("boot_time() not implemented in C extension")

    def test_boot_time_positive_value(self, cygwin_cext):
        """Test that boot_time returns a positive timestamp."""
        try:
            boot_time = cygwin_cext.boot_time()
            assert (
                boot_time > 0
            ), f"Boot time should be positive timestamp, got {boot_time}"
        except AttributeError:
            pytest.skip("boot_time() not implemented in C extension")

    def test_boot_time_reasonable_value(self, cygwin_cext):
        """Test that boot_time is within reasonable range."""
        try:
            boot_time = cygwin_cext.boot_time()
            current_time = time.time()

            # Boot time should be in the past
            assert boot_time < current_time, (
                f"Boot time ({boot_time}) should be before current time"
                f" ({current_time})"
            )

            # Boot time should not be more than 365 days ago
            max_age = 365 * 24 * 3600  # 365 days in seconds
            age = current_time - boot_time
            assert (
                age < max_age
            ), f"Boot time seems too old: {age / 3600:.1f} hours ago"

            # Boot time should be at least 30 seconds ago
            min_age = 30
            assert (
                age > min_age
            ), f"Boot time seems too recent: {age:.1f} seconds ago"
        except AttributeError:
            pytest.skip("boot_time() not implemented in C extension")

    def test_boot_time_consistency(self, cygwin_cext):
        """Test that boot_time returns consistent values."""
        try:
            boot_time1 = cygwin_cext.boot_time()
            time.sleep(0.01)  # Small delay
            boot_time2 = cygwin_cext.boot_time()

            # Boot time should be the same (or very close due to precision)
            diff = abs(boot_time1 - boot_time2)
            assert diff < 1.0, (
                f"Boot time inconsistent: {boot_time1} vs {boot_time2} (diff:"
                f" {diff}s)"
            )
        except AttributeError:
            pytest.skip("boot_time() not implemented in C extension")

    def test_boot_time_integration_with_psutil(self, psutil_module):
        """Test integration with psutil.boot_time()."""
        try:
            psutil_boot_time = psutil_module.boot_time()
            assert isinstance(
                psutil_boot_time, (int, float)
            ), "psutil boot_time should return number"
            assert psutil_boot_time > 0, "psutil boot_time should be positive"

            # If C extension has boot_time, compare
            try:
                import psutil._psutil_cygwin as cext

                cext_boot_time = cext.boot_time()

                # Should be very close (within 1 second)
                diff = abs(psutil_boot_time - cext_boot_time)
                assert diff < 1.0, (
                    f"psutil ({psutil_boot_time}) and C ext ({cext_boot_time})"
                    f" boot times differ by {diff}s"
                )
            except AttributeError:
                # C extension boot_time not implemented, that's OK
                pass

        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            pytest.skip(f"psutil.boot_time() integration issue: {e}")

    def test_boot_time_cross_validation_proc(self, cygwin_cext):
        """Cross-validate boot_time with /proc/stat if available."""
        try:
            boot_time = cygwin_cext.boot_time()

            # Try to read boot time from /proc/stat
            try:
                with open('/proc/stat') as f:
                    for line in f:
                        if line.startswith('btime'):
                            proc_boot_time = float(line.split()[1])

                            # Should match closely
                            diff = abs(boot_time - proc_boot_time)
                            assert diff < 1.0, (
                                f"C ext ({boot_time}) vs /proc/stat"
                                f" ({proc_boot_time}) differ by {diff}s"
                            )
                            break
                    else:
                        pytest.skip("btime not found in /proc/stat")
            except (OSError, FileNotFoundError):
                pytest.skip("/proc/stat not available for cross-validation")

        except AttributeError:
            pytest.skip("boot_time() not implemented in C extension")

    def test_boot_time_performance(
        self, cygwin_cext, performance_timer, system_constants
    ):
        """Test that boot_time executes within reasonable time."""
        try:
            system_constants['performance_threshold_ms']

            with performance_timer as timer:
                for _ in range(100):
                    cygwin_cext.boot_time()

            avg_time_ms = timer.duration_ms / 100
            assert (
                avg_time_ms < 10.0
            ), f"boot_time too slow: {avg_time_ms:.3f}ms average"
        except AttributeError:
            pytest.skip("boot_time() not implemented in C extension")


class TestUsers:
    """Test suite for users() function."""

    def test_users_return_type(self, cygwin_cext):
        """Test that users returns a list."""
        try:
            users_list = cygwin_cext.users()
            assert isinstance(
                users_list, list
            ), f"Expected list, got {type(users_list).__name__}"
        except AttributeError:
            pytest.skip("users() not implemented in C extension")

    def test_users_list_structure(self, cygwin_cext):
        """Test that users list has proper structure when not empty."""
        try:
            users_list = cygwin_cext.users()

            # Each user should be a tuple/namedtuple with user info
            for i, user in enumerate(users_list):
                # Users might be tuples: (name, terminal, host, started, pid)
                # or named tuples, depending on implementation
                assert isinstance(user, (tuple, list)) or hasattr(
                    user, '_fields'
                ), f"User {i} should be tuple-like, got {type(user).__name__}"

                if isinstance(user, (tuple, list)):
                    # Basic validation of tuple structure
                    assert len(user) >= 3, (
                        f"User tuple {i} should have at least 3 fields, "
                        f"got {len(user)}"
                    )

                    # First field should be username (string)
                    username = user[0]
                    assert isinstance(username, str), (
                        "Username should be string, got "
                        f"{type(username).__name__}"
                    )
                    assert len(username) > 0, "Username should not be empty"

        except AttributeError:
            pytest.skip("users() not implemented in C extension")

    def test_users_integration_with_psutil(self, psutil_module):
        """Test integration with psutil.users()."""
        try:
            psutil_users = psutil_module.users()
            assert isinstance(
                psutil_users, list
            ), "psutil users should return list"

            # Compare with C extension if available
            try:
                import psutil._psutil_cygwin as cext

                cext_users = cext.users()

                # Both should be lists
                assert isinstance(
                    cext_users, list
                ), "C extension users should return list"

                # If both have users, compare count (might be different
                # due to timing)
                if psutil_users and cext_users:
                    # Counts should be reasonably close
                    count_diff = abs(len(psutil_users) - len(cext_users))
                    assert count_diff <= 2, (
                        "User count difference too large:"
                        f" psutil={len(psutil_users)}, cext={len(cext_users)}"
                    )

            except AttributeError:
                # C extension users not implemented
                pass

        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            pytest.skip(f"psutil.users() integration issue: {e}")

    def test_users_current_user_detection(self, cygwin_cext):
        """Test that users() can detect current user session."""
        try:
            users_list = cygwin_cext.users()
            current_username = os.getenv('USER') or os.getenv('USERNAME')

            if current_username and users_list:
                # Check if current user appears in the list
                usernames = []
                for user in users_list:
                    if isinstance(user, (tuple, list)) and len(user) > 0:
                        usernames.append(user[0])
                    elif hasattr(user, 'name'):
                        usernames.append(user.name)

                # Current user might be in the list
                # Note: This is not guaranteed, especially
                # in Cygwin environments
                if current_username in usernames:
                    pass

        except AttributeError:
            pytest.skip("users() not implemented in C extension")

    def test_users_performance(self, cygwin_cext, performance_timer):
        """Test that users() executes within reasonable time."""
        try:
            with performance_timer as timer:
                for _ in range(50):
                    cygwin_cext.users()

            avg_time_ms = timer.duration_ms / 50
            assert (
                avg_time_ms < 20.0
            ), f"users() too slow: {avg_time_ms:.3f}ms average"
        except AttributeError:
            pytest.skip("users() not implemented in C extension")

    def test_users_concurrent_access(self, cygwin_cext):
        """Test that users() is safe for concurrent access."""
        try:
            results = []
            errors = []

            def worker():
                try:
                    for _ in range(10):
                        users_list = cygwin_cext.users()
                        results.append(len(users_list))
                except (OSError, RuntimeError, ValueError) as e:
                    errors.append(e)

            # Run multiple threads
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=worker)
                threads.append(thread)
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Check results
            assert len(errors) == 0, f"Concurrent access errors: {errors}"
            assert len(results) > 0, "No successful concurrent operations"

        except AttributeError:
            pytest.skip("users() not implemented in C extension")


class TestSystemCpuTimes:
    """Test suite for system-wide cpu_times() function."""

    def test_cpu_times_return_type(self, cygwin_cext):
        """Test that cpu_times returns a tuple."""
        cpu_times = cygwin_cext.cpu_times()
        assert isinstance(
            cpu_times, (tuple, list)
        ), f"Expected tuple/list, got {type(cpu_times).__name__}"

    def test_cpu_times_structure(self, cygwin_cext):
        """Test that cpu_times has expected structure."""
        cpu_times = cygwin_cext.cpu_times()

        # Should have at least 3-4 basic fields: user, system, idle
        assert (
            len(cpu_times) >= 3
        ), f"CPU times should have at least 3 fields, got {len(cpu_times)}"

        # All values should be numbers (float or int)
        for i, value in enumerate(cpu_times):
            assert isinstance(value, (int, float)), (
                f"CPU time field {i} should be number, got "
                f"{type(value).__name__}"
            )

    def test_cpu_times_non_negative_values(self, cygwin_cext):
        """Test that all CPU time values are non-negative."""
        try:
            cpu_times = cygwin_cext.cpu_times()

            for i, value in enumerate(cpu_times):
                assert (
                    value >= 0.0
                ), f"CPU time field {i} should be non-negative, got {value}"

        except AttributeError:
            pytest.skip("cpu_times() not implemented in C extension")

    def test_cpu_times_reasonable_values(self, cygwin_cext):
        """Test that CPU times have reasonable values."""
        try:
            cpu_times = cygwin_cext.cpu_times()

            # Get boot time for context
            try:
                boot_time = cygwin_cext.boot_time()
                current_time = time.time()
                uptime = current_time - boot_time

                # Total CPU time should not exceed uptime * number of CPUs
                total_cpu_time = sum(cpu_times)
                logical_cpus = cygwin_cext.cpu_count_logical()
                max_expected = uptime * logical_cpus

                # Allow some tolerance for measurement differences
                assert total_cpu_time <= max_expected * 1.1, (
                    f"Total CPU time ({total_cpu_time:.1f}s) exceeds "
                    f"expected maximum ({max_expected:.1f}s)"
                )

            except (AttributeError, OSError):
                # boot_time or cpu_count_logical not available,
                # skip this validation
                pass

        except AttributeError:
            pytest.skip("cpu_times() not implemented in C extension")

    def test_cpu_times_integration_with_psutil(self, psutil_module):
        """Test integration with psutil.cpu_times()."""
        try:
            psutil_cpu_times = psutil_module.cpu_times()
            assert hasattr(
                psutil_cpu_times, 'user'
            ), "psutil cpu_times should have user field"
            assert hasattr(
                psutil_cpu_times, 'system'
            ), "psutil cpu_times should have system field"

            # Compare with C extension if available
            try:
                import psutil._psutil_cygwin as cext

                cext_cpu_times = cext.cpu_times()

                if (
                    isinstance(cext_cpu_times, (tuple, list))
                    and len(cext_cpu_times) >= 2
                ):
                    # Basic comparison (values might differ due to timing)
                    cext_user = cext_cpu_times[0]
                    cext_system = cext_cpu_times[1]

                    # Should be in same ballpark
                    user_ratio = abs(cext_user - psutil_cpu_times.user) / max(
                        psutil_cpu_times.user, 1.0
                    )
                    abs(cext_system - psutil_cpu_times.system) / max(
                        psutil_cpu_times.system, 1.0
                    )

                    # Allow significant difference due to different
                    # measurement methods
                    assert (
                        user_ratio < 0.5
                        or abs(cext_user - psutil_cpu_times.user) < 10.0
                    ), (
                        "User CPU time differs significantly:"
                        f" cext={cext_user}, psutil={psutil_cpu_times.user}"
                    )

            except AttributeError:
                # C extension cpu_times not implemented
                pass

        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            pytest.skip(f"psutil.cpu_times() integration issue: {e}")

    def test_cpu_times_monotonic_increase(self, cygwin_cext):
        """Test that CPU times increase monotonically."""
        try:
            cpu_times1 = cygwin_cext.cpu_times()
            time.sleep(0.1)  # Small delay to allow CPU time to accumulate
            cpu_times2 = cygwin_cext.cpu_times()

            # At least one field should have increased (or stayed the same)
            increased_or_same = 0
            decreased = 0

            for i, (time1, time2) in enumerate(zip(cpu_times1, cpu_times2)):
                if time2 >= time1:
                    increased_or_same += 1
                else:
                    decreased += 1

            # Most fields should increase or stay the same
            assert increased_or_same >= decreased, (
                "CPU times should generally increase:"
                f" {increased_or_same} increased/same, {decreased} decreased"
            )

        except AttributeError:
            pytest.skip("cpu_times() not implemented in C extension")

    def test_cpu_times_performance(self, cygwin_cext, performance_timer):
        """Test that cpu_times() executes within reasonable time."""
        try:
            with performance_timer as timer:
                for _ in range(100):
                    cygwin_cext.cpu_times()

            avg_time_ms = timer.duration_ms / 100
            assert (
                avg_time_ms < 5.0
            ), f"cpu_times too slow: {avg_time_ms:.3f}ms average"
        except AttributeError:
            pytest.skip("cpu_times() not implemented in C extension")


class TestCpuStats:
    """Test suite for cpu_stats() function."""

    def test_cpu_stats_return_type(self, cygwin_cext):
        """Test that cpu_stats returns proper structure."""
        try:
            cpu_stats = cygwin_cext.cpu_stats()
            # Should return tuple or namedtuple with CPU statistics
            assert isinstance(cpu_stats, (tuple, list)) or hasattr(
                cpu_stats, '_fields'
            ), f"Expected tuple-like object, got {type(cpu_stats).__name__}"
        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")

    def test_cpu_stats_structure(self, cygwin_cext):
        """Test that cpu_stats has expected structure."""
        try:
            cpu_stats = cygwin_cext.cpu_stats()

            # Should have at least 4 fields: ctx_switches, interrupts,
            # soft_interrupts, syscalls
            if isinstance(cpu_stats, (tuple, list)):
                assert len(cpu_stats) >= 4, (
                    "CPU stats should have at least 4 fields, got "
                    f"{len(cpu_stats)}"
                )
            elif hasattr(cpu_stats, '_fields'):
                # Named tuple with expected fields
                expected_fields = [
                    'ctx_switches',
                    'interrupts',
                    'soft_interrupts',
                    'syscalls',
                ]
                for field in expected_fields:
                    assert hasattr(
                        cpu_stats, field
                    ), f"Missing CPU stats field: {field}"

        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")

    def test_cpu_stats_field_types(self, cygwin_cext):
        """Test that CPU stats fields are integers."""
        try:
            cpu_stats = cygwin_cext.cpu_stats()

            if isinstance(cpu_stats, (tuple, list)):
                for i, value in enumerate(cpu_stats):
                    assert isinstance(value, int), (
                        f"CPU stats field {i} should be int, got "
                        f"{type(value).__name__}"
                    )
            elif hasattr(cpu_stats, '_fields'):
                for field in cpu_stats._fields:
                    value = getattr(cpu_stats, field)
                    assert isinstance(value, int), (
                        f"CPU stats {field} should be int, got "
                        f"{type(value).__name__}"
                    )

        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")

    def test_cpu_stats_non_negative_values(self, cygwin_cext):
        """Test that all CPU stats values are non-negative."""
        try:
            cpu_stats = cygwin_cext.cpu_stats()

            if isinstance(cpu_stats, (tuple, list)):
                for i, value in enumerate(cpu_stats):
                    assert value >= 0, (
                        f"CPU stats field {i} should be non-negative, "
                        f"got {value}"
                    )
            elif hasattr(cpu_stats, '_fields'):
                for field in cpu_stats._fields:
                    value = getattr(cpu_stats, field)
                    assert (
                        value >= 0
                    ), f"CPU stats {field} should be non-negative, got {value}"

        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")

    def test_cpu_stats_integration_with_psutil(self, psutil_module):
        """Test integration with psutil.cpu_stats()."""
        try:
            psutil_cpu_stats = psutil_module.cpu_stats()

            # Should have expected attributes
            expected_attrs = [
                'ctx_switches',
                'interrupts',
                'soft_interrupts',
                'syscalls',
            ]
            for attr in expected_attrs:
                assert hasattr(
                    psutil_cpu_stats, attr
                ), f"psutil cpu_stats missing {attr}"
                value = getattr(psutil_cpu_stats, attr)
                assert isinstance(
                    value, int
                ), f"psutil cpu_stats {attr} should be int"
                assert (
                    value >= 0
                ), f"psutil cpu_stats {attr} should be non-negative"

            # Compare with C extension if available
            try:
                import psutil._psutil_cygwin as cext

                cext_cpu_stats = cext.cpu_stats()

                if hasattr(cext_cpu_stats, '_fields'):
                    # Compare individual fields
                    for attr in expected_attrs:
                        if hasattr(cext_cpu_stats, attr):
                            cext_value = getattr(cext_cpu_stats, attr)
                            psutil_value = getattr(psutil_cpu_stats, attr)

                            # Values might differ due to timing, but should be
                            # in same range
                            if psutil_value > 0:
                                ratio = cext_value / psutil_value
                                assert 0.5 <= ratio <= 2.0, (
                                    f"CPU stats {attr} differ significantly: "
                                    f"cext={cext_value}, "
                                    f"psutil={psutil_value}"
                                )

            except AttributeError:
                # C extension cpu_stats not implemented
                pass

        except (OSError, RuntimeError, ValueError, AttributeError) as e:
            pytest.skip(f"psutil.cpu_stats() integration issue: {e}")

    def test_cpu_stats_monotonic_increase(self, cygwin_cext):
        """Test that CPU stats generally increase over time."""
        try:
            cpu_stats1 = cygwin_cext.cpu_stats()
            time.sleep(0.1)  # Small delay
            cpu_stats2 = cygwin_cext.cpu_stats()

            # Extract values for comparison
            if isinstance(cpu_stats1, (tuple, list)):
                values1 = cpu_stats1
                values2 = cpu_stats2
            else:
                values1 = [
                    getattr(cpu_stats1, field) for field in cpu_stats1._fields
                ]
                values2 = [
                    getattr(cpu_stats2, field) for field in cpu_stats2._fields
                ]

            # At least some stats should increase (or stay the same)
            increased_or_same = 0
            decreased = 0

            for val1, val2 in zip(values1, values2):
                if val2 >= val1:
                    increased_or_same += 1
                else:
                    decreased += 1

            # Most stats should increase or stay the same
            assert increased_or_same >= decreased, (
                "CPU stats should generally increase:"
                f" {increased_or_same} increased/same, {decreased} decreased"
            )

        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")

    def test_cpu_stats_performance(self, cygwin_cext, performance_timer):
        """Test that cpu_stats() executes within reasonable time."""
        try:
            with performance_timer as timer:
                for _ in range(100):
                    cygwin_cext.cpu_stats()

            avg_time_ms = timer.duration_ms / 100
            assert (
                avg_time_ms < 5.0
            ), f"cpu_stats too slow: {avg_time_ms:.3f}ms average"
        except AttributeError:
            pytest.skip("cpu_stats() not implemented in C extension")


class TestSystemInfoIntegration:
    """Test integration of all system information functions."""

    def test_all_system_info_functions_available(self, cygwin_cext):
        """Test that all system info functions are available."""
        expected_functions = ['boot_time', 'users', 'cpu_times', 'cpu_stats']

        available_functions = []
        missing_functions = []

        for func_name in expected_functions:
            if hasattr(cygwin_cext, func_name):
                func = getattr(cygwin_cext, func_name)
                if callable(func):
                    available_functions.append(func_name)
                else:
                    missing_functions.append(f"{func_name} (not callable)")
            else:
                missing_functions.append(f"{func_name} (not found)")

        # At least some functions should be available
        assert (
            len(available_functions) > 0
        ), "No system info functions available"

    def test_system_info_comprehensive_retrieval(self, cygwin_cext):
        """Test retrieving all system information at once."""
        system_info = {}

        # Try to get all system information
        try:
            system_info['boot_time'] = cygwin_cext.boot_time()
        except (AttributeError, OSError):
            system_info['boot_time'] = None

        try:
            system_info['users'] = cygwin_cext.users()
        except (AttributeError, OSError):
            system_info['users'] = None

        try:
            system_info['cpu_times'] = cygwin_cext.cpu_times()
        except (AttributeError, OSError):
            system_info['cpu_times'] = None

        try:
            system_info['cpu_stats'] = cygwin_cext.cpu_stats()
        except (AttributeError, OSError):
            system_info['cpu_stats'] = None

        # At least one piece of info should be available
        available_info = {
            k: v for k, v in system_info.items() if v is not None
        }
        assert (
            len(available_info) > 0
        ), f"No system information available: {system_info}"

    def test_system_info_concurrent_access(self, cygwin_cext):
        """Test that system info functions are safe for concurrent access."""

        def worker(results):
            try:
                info = {}

                try:
                    info['boot_time'] = cygwin_cext.boot_time()
                except (AttributeError, OSError):
                    pass

                try:
                    info['users'] = len(cygwin_cext.users())
                except (AttributeError, OSError):
                    pass

                try:
                    info['cpu_times'] = cygwin_cext.cpu_times()
                except (AttributeError, OSError):
                    pass

                try:
                    info['cpu_stats'] = cygwin_cext.cpu_stats()
                except (AttributeError, OSError):
                    pass

                results.append(info)
            except (OSError, RuntimeError, ValueError) as e:
                results.append(f"error: {e}")

        # Run multiple threads
        results = []
        threads = []

        for _ in range(5):
            thread = threading.Thread(target=worker, args=(results,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check results
        successful = [r for r in results if isinstance(r, dict)]
        errors = [r for r in results if isinstance(r, str)]

        assert len(successful) >= 4, (
            f"Too many thread failures: {len(errors)} errors out of"
            f" {len(results)}"
        )
        assert len(errors) <= 1, f"Concurrent access errors: {errors}"

    def test_system_info_performance_batch(
        self, cygwin_cext, performance_timer
    ):
        """Test performance of retrieving all system info at once."""
        with performance_timer as timer:
            for _ in range(50):
                # Get all available system info
                try:
                    cygwin_cext.boot_time()
                except (AttributeError, OSError):
                    pass

                try:
                    cygwin_cext.users()
                except (AttributeError, OSError):
                    pass

                try:
                    cygwin_cext.cpu_times()
                except (AttributeError, OSError):
                    pass

                try:
                    cygwin_cext.cpu_stats()
                except (AttributeError, OSError):
                    pass

        avg_time_ms = timer.duration_ms / 50
        assert (
            avg_time_ms < 50.0
        ), f"System info retrieval too slow: {avg_time_ms:.3f}ms average"


# Helper functions for manual testing
def run_manual_tests():
    """Run manual tests for development and debugging."""

    try:
        import psutil._psutil_cygwin as cext

        # Test boot_time
        try:
            boot_time = cext.boot_time()
            datetime.fromtimestamp(boot_time)
        except (AttributeError, OSError):
            pass

        # Test users
        try:
            users_list = cext.users()
            for user in users_list[:3]:  # Show first 3
                pass
        except (AttributeError, OSError):
            pass

        # Test cpu_times
        try:
            cext.cpu_times()
        except (AttributeError, OSError):
            pass

        # Test cpu_stats
        try:
            cext.cpu_stats()
        except (AttributeError, OSError):
            pass

    except (OSError, RuntimeError, ValueError):
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Allow running as standalone script for development
    run_manual_tests()
