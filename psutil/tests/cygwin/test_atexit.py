#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Test for atexit permission error bug (Issue 008)

This test validates that psutil's cleanup code properly handles permission
errors when accessing system processes during Python shutdown.

Bug Description:
During atexit cleanup, _ppid_map() tries to build PID-to-parent mapping for
ALL processes, including system processes like cygrunsrv (PID 790). When access
is denied to system processes, the error should be caught and handled
gracefully, not propagated as an unhandled exception during atexit cleanup.

Expected Behavior:
- System process access should either succeed or raise AccessDenied
- _ppid_map() should handle AccessDenied exceptions gracefully
- atexit cleanup should complete without unhandled exceptions
- Process iteration should be resilient to permission errors
"""

import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import threading

import pytest

logger = logging.getLogger(__name__)


class TestAtexitPermissionBug:
    """Test suite for Issue 008 - atexit permission error bug"""

    def test_system_process_identification(self, psutil_module):
        """Verify we can identify system processes that may cause permission
        errors.
        """
        system_processes = []

        # Look for known system processes that typically run as SYSTEM
        target_names = ['cygrunsrv', 'cron', 'sshd']

        for proc in psutil_module.process_iter(['pid', 'name', 'username']):
            try:
                info = proc.info
                if info['name'] in target_names or info['username'] in {
                    'System',
                    'root',
                    'SYSTEM',
                }:
                    system_processes.append({
                        'pid': info['pid'],
                        'name': info['name'],
                        'username': info['username'],
                    })
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                pass

        if len(system_processes) == 0:
            pytest.skip("No system processes found for testing")

        logger.info(
            "Found %d system processes for testing:", len(system_processes)
        )
        for proc in system_processes[:3]:  # Show first 3
            logger.info(
                "  PID %d: %s (%s)",
                proc['pid'],
                proc['name'],
                proc['username'],
            )

    def test_ppid_access_permission_handling(self, psutil_module):
        """Test that ppid access handles permission errors correctly"""
        permission_errors = 0
        successful_access = 0
        no_such_process = 0

        # Test access to various processes, especially system ones
        for proc in psutil_module.process_iter(['pid', 'name']):
            try:
                ppid = proc.ppid()
                successful_access += 1
                assert isinstance(
                    ppid, int
                ), f"ppid should be integer, got {type(ppid)}"
            except psutil_module.AccessDenied:
                permission_errors += 1
                # This is expected and acceptable
            except psutil_module.NoSuchProcess:
                no_such_process += 1
                # Also acceptable - process disappeared
            except (OSError, PermissionError) as e:
                pytest.fail(
                    f"Unexpected error accessing PID {proc.pid}:"
                    f" {type(e).__name__}: {e}"
                )

        logger.info("ppid access results:")
        logger.info("  Successful: %d", successful_access)
        logger.info("  Permission denied: %d", permission_errors)
        logger.info("  Process disappeared: %d", no_such_process)

        # Should have accessed some processes successfully
        assert (
            successful_access > 0
        ), "Should have successfully accessed some processes"

        # Permission errors are expected and should be handled gracefully
        if permission_errors > 0:
            logger.info(
                "✓ Gracefully handled %d permission errors", permission_errors
            )

    def test_ppid_map_error_resilience(self, psutil_module):
        """Test that _ppid_map handles permission errors gracefully"""
        try:
            from psutil import _ppid_map
        except ImportError:
            pytest.skip("_ppid_map function not accessible")

        # This is the function that causes the atexit error
        # It should handle permission errors internally
        try:
            pid_map = _ppid_map()
        except (OSError, PermissionError, psutil_module.AccessDenied) as e:
            pytest.fail(
                "_ppid_map should handle permission errors gracefully:"
                f" {type(e).__name__}: {e}"
            )

        # Validate the result
        assert isinstance(
            pid_map, dict
        ), "_ppid_map should return a dictionary"

        # Should contain some entries (at least current process)
        assert len(pid_map) > 0, "_ppid_map should return non-empty mapping"

        # Validate structure - all keys and values should be integers (PIDs)
        for child_pid, parent_pid in pid_map.items():
            assert isinstance(
                child_pid, int
            ), f"Child PID should be int: {child_pid}"
            assert isinstance(
                parent_pid, int
            ), f"Parent PID should be int: {parent_pid}"
            assert child_pid > 0, f"Child PID should be positive: {child_pid}"
            assert (
                parent_pid >= 0
            ), (  # 0 for kernel processes
                f"Parent PID should be non-negative: {parent_pid}"
            )

    def test_atexit_cleanup_simulation(self, psutil_module):
        """Simulate the atexit cleanup that causes the original bug"""

        # Create a script that reproduces the problematic atexit behavior
        test_script = textwrap.dedent(f"""
            import sys
            import atexit
            import os

            # Add psutil path
            sys.path.insert(0, '{os.path.dirname(psutil_module.__file__)}/..')

            def problematic_cleanup():
                '''Reproduce the cleanup behavior that caused the bug'''
                try:
                    import psutil
                    from psutil import _ppid_map

                    # This is what happens in the original bug:
                    # During cleanup, _ppid_map() is called and tries to
                    # access system processes, causing PermissionError for
                    # PID 790 (cygrunsrv)
                    pid_map = _ppid_map()

                    # If we get here without exception, the bug is fixed
                    print(f"CLEANUP_SUCCESS: Generated PID map with "
                          f"{{len(pid_map)}} entries")

                except PermissionError as e:
                    # This is the original bug - should not happen
                    print(f"CLEANUP_PERMISSION_ERROR: {{e}}")
                except psutil.AccessDenied as e:
                    # This is the translated error - should not propagate
                    # to atexit
                    print(f"CLEANUP_ACCESS_DENIED: {{e}}")
                except (OSError, RuntimeError) as e:
                    # Any other error is also a problem
                    print("CLEANUP_OTHER_ERROR: %s: %s" % (
                        type(e).__name__, e
                    ))
                    import traceback
                    traceback.print_exc()

            # Register the cleanup function (this is what causes the atexit
            # error)
            atexit.register(problematic_cleanup)

            # Simulate normal psutil usage that might trigger the issue
            import psutil

            # Access some processes to populate internal state
            current = psutil.Process()
            current.name()

            # Try to access system processes (like the test suite does)
            system_pids = []
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] in ['cygrunsrv', 'cron']:
                        system_pids.append(proc.info['pid'])
                        # Try to access ppid - this might cache problematic
                        # state
                        try:
                            proc.ppid()
                        except (OSError, PermissionError, ImportError):
                            pass
                except (OSError, PermissionError, psutil_module.AccessDenied):
                    pass
                if len(system_pids) >= 2:  # Found enough for testing
                    break

            print(f"MAIN_COMPLETE: Found {{len(system_pids)}} system "
                  f"processes")
            # Script ends here - atexit cleanup runs and should NOT fail
        """)

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as f:
            f.write(test_script)
            script_path = f.name

        try:
            # Execute the script and capture all output
            result = subprocess.run(
                [sys.executable, script_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )

            output = result.stdout + result.stderr
            logger.info("Atexit simulation output:")
            for line in output.split('\n'):
                if line.strip():
                    logger.info("  %s", line)

            # Analyze the results
            if "CLEANUP_PERMISSION_ERROR" in output:
                pytest.fail(
                    "Original PermissionError bug reproduced - fix"
                    f" needed:\n{output}"
                )

            if "CLEANUP_ACCESS_DENIED" in output:
                pytest.fail(
                    "AccessDenied error propagated to atexit - fix"
                    f" needed:\n{output}"
                )

            if "CLEANUP_OTHER_ERROR" in output:
                pytest.fail(
                    "Other error during cleanup - investigation"
                    f" needed:\n{output}"
                )

            if "CLEANUP_SUCCESS" not in output and result.returncode != 0:
                pytest.fail(
                    "Atexit cleanup did not complete successfully (exit code"
                    f" {result.returncode}):\n{output}"
                )

            # If we reach here, cleanup was successful
            assert "MAIN_COMPLETE" in output, "Main execution should complete"

        finally:
            # Clean up temporary file
            os.unlink(script_path)

    def test_cygrunsrv_specific_handling(self, psutil_module):
        """Test specific handling of cygrunsrv process (the one mentioned in
        bug report).
        """

        # Look for cygrunsrv specifically - use multiple detection methods
        cygrunsrv_procs = []

        # Method 1: Search by name (case-insensitive)
        for proc in psutil_module.process_iter(['pid', 'name']):
            try:
                proc_name = (proc.info.get('name') or '').lower()
                if 'cygrunsrv' in proc_name:
                    cygrunsrv_procs.append(proc)
            except (psutil_module.NoSuchProcess, psutil_module.AccessDenied):
                pass

        # Method 2: Try known PID 790 from ps output
        if not cygrunsrv_procs:
            try:
                proc = psutil_module.Process(790)
                name = proc.name().lower()
                if 'cygrunsrv' in name:
                    cygrunsrv_procs.append(proc)
            except (OSError, PermissionError, psutil_module.AccessDenied):
                pass

        # Method 3: Look among System processes
        if not cygrunsrv_procs:
            for proc in psutil_module.process_iter(
                ['pid', 'name', 'username']
            ):
                try:
                    info = proc.info
                    if (
                        info.get('username') == 'System'
                        and 'cygrunsrv' in (info.get('name') or '').lower()
                    ):
                        cygrunsrv_procs.append(proc)
                except (
                    psutil_module.NoSuchProcess,
                    psutil_module.AccessDenied,
                ):
                    pass

        if not cygrunsrv_procs:
            # Final check with system ps command
            try:
                import subprocess

                result = subprocess.run(
                    ['ps', '-eaf'], check=False, capture_output=True, text=True
                )
                if 'cygrunsrv' in result.stdout:
                    pytest.fail(
                        "cygrunsrv is running (visible in ps) but psutil"
                        " cannot detect it"
                    )
                else:
                    pytest.skip("cygrunsrv process genuinely not running")
            except (OSError, PermissionError, psutil_module.AccessDenied):
                pytest.skip(
                    "cygrunsrv process not found and cannot verify with ps"
                )

        logger.info("Found %d cygrunsrv process(es)", len(cygrunsrv_procs))

        # Test each cygrunsrv process
        for proc in cygrunsrv_procs:
            logger.info("Testing cygrunsrv PID %d...", proc.pid)

            # Test ppid access - this is what failed in the original bug
            try:
                ppid = proc.ppid()
                logger.info("  Successfully got parent PID: %d", ppid)
                assert isinstance(ppid, int), "Parent PID should be integer"
            except psutil_module.AccessDenied as e:
                logger.info("  Access denied (expected): %s", e)
                # This is acceptable - should be handled gracefully
            except psutil_module.NoSuchProcess as e:
                logger.info("  Process disappeared: %s", e)
                # Also acceptable
            except (OSError, PermissionError) as e:
                pytest.fail(
                    f"Unexpected error accessing cygrunsrv PID {proc.pid}:"
                    f" {type(e).__name__}: {e}"
                )

    def test_concurrent_system_process_access(self, psutil_module):
        """Test concurrent access to system processes (stress test for
        robustness).
        """

        # Find some system processes to test
        system_pids = []
        for proc in psutil_module.process_iter(['pid', 'name', 'username']):
            try:
                info = proc.info
                if info['username'] in {'System', 'root'} or info['name'] in {
                    'cygrunsrv',
                    'cron',
                    'sshd',
                }:
                    system_pids.append(info['pid'])
                    if len(system_pids) >= 5:  # Limit for testing
                        break
            except (OSError, PermissionError, psutil_module.AccessDenied):
                pass

        if not system_pids:
            pytest.skip("No system processes found for concurrent testing")

        logger.info(
            "Testing concurrent access to %d system processes",
            len(system_pids),
        )

        errors = []
        successful = []

        def access_process(pid):
            """Access a process and record result"""
            try:
                proc = psutil_module.Process(pid)
                _ppid = proc.ppid()
                successful.append(pid)
            except (psutil_module.AccessDenied, psutil_module.NoSuchProcess):
                # These are expected and acceptable
                pass
            except (OSError, PermissionError) as e:
                errors.append(f"PID {pid}: {type(e).__name__}: {e}")

        # Create multiple threads to access processes concurrently
        threads = []
        for pid in system_pids:
            for _ in range(3):  # 3 attempts per PID
                thread = threading.Thread(target=access_process, args=(pid,))
                threads.append(thread)
                thread.start()

        # Wait for all threads with timeout
        for thread in threads:
            thread.join(timeout=2)  # Don't wait too long

        # Check results
        logger.info("Concurrent access results:")
        logger.info("  Successful accesses: %d", len(successful))
        logger.info("  Errors: %d", len(errors))

        # Should not have any unexpected errors
        assert (
            len(errors) == 0
        ), f"Unexpected errors during concurrent access: {errors}"

    def test_process_cleanup_robustness(self, psutil_module):
        """Test that process object cleanup is robust"""

        # Create many process objects, including for system processes
        processes = []

        # Create process objects for various PIDs
        for proc_info in psutil_module.process_iter(['pid']):
            try:
                proc = psutil_module.Process(proc_info.info['pid'])
                processes.append(proc)
                if len(processes) >= 20:  # Limit for testing
                    break
            except (OSError, PermissionError, psutil_module.AccessDenied):
                pass

        logger.info("Created %d process objects", len(processes))

        # Access some properties to populate internal state
        accessible = 0
        for proc in processes:
            try:
                _name = proc.name()  # This might populate internal caches
                accessible += 1
            except (OSError, PermissionError, psutil_module.AccessDenied):
                pass

        logger.info(
            "Successfully accessed properties of %d processes", accessible
        )

        # Now let processes be garbage collected
        # This might trigger cleanup code that could cause issues
        del processes

        # Force garbage collection to trigger any cleanup
        import gc

        gc.collect()

        # If we reach here without issues, cleanup is working properly
        assert True  # Test passes if no exceptions during cleanup


def test_atexit_bug_integration():
    """Main integration test for the atexit permission bug"""
    import psutil

    # Run the critical test that would expose the bug
    test_instance = TestAtexitPermissionBug()
    test_instance.test_ppid_map_error_resilience(psutil)
    test_instance.test_atexit_cleanup_simulation(psutil)


if __name__ == "__main__":
    # Allow running as standalone script for manual testing
    import psutil

    logger.info("Testing atexit permission error bug (Issue 008)")
    logger.info("%s", "=" * 60)

    test_instance = TestAtexitPermissionBug()

    try:
        test_instance.test_system_process_identification(psutil)
        test_instance.test_ppid_access_permission_handling(psutil)
        test_instance.test_ppid_map_error_resilience(psutil)
        test_instance.test_cygrunsrv_specific_handling(psutil)
        test_instance.test_atexit_cleanup_simulation(psutil)

        logger.info("\n%s", "=" * 60)
        logger.info(
            "✓ All tests passed - atexit permission bug appears to be "
            "fixed or not present"
        )

    except Exception:
        logger.exception("\n✗ Test failed")
        import traceback

        traceback.print_exc()
        sys.exit(1)
