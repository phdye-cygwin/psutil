#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Memory Management Tests - Cygwin Platform

Tests memory-related functionality in Cygwin implementation:
- virtual_memory(): System virtual memory information
- swap_memory(): System swap memory information
- Process memory functions: memory_info(), memory_full_info(), memory_maps()

Test Coverage:
- Return type and structure validation
- Field type validation and value ranges
- Mathematical consistency checks
- Cross-validation with psutil public API
- Performance characteristics
- Error handling and edge cases
- Integration testing

Source Migration:
- Migrated from issue/phase-2/tests/test_phase2_memory.py
- Migrated from issue/phase-4/tests/test_phase_4_2.py
- Consolidated memory-related tests from multiple phases

Functions Covered:
- virtual_memory() -> tuple[int, int, int, int, int, int, int]
- swap_memory() -> tuple[int, int, int, float, int, int]
- proc_memory_full_info(pid) -> tuple[int, int, int, int, int, int, int, int,
                                        int, int]
- proc_memory_maps(pid) -> list[tuple[...]]
"""
import os

import pytest

import psutil


class TestVirtualMemory:
    """Test suite for virtual_memory() function."""

    def test_virtual_memory_return_type(self, cygwin_cext):
        """Test that virtual_memory returns a tuple."""
        vmem = cygwin_cext.virtual_memory()
        assert isinstance(
            vmem, tuple
        ), f"Expected tuple, got {type(vmem).__name__}"

    def test_virtual_memory_tuple_length(self, cygwin_cext):
        """Test that virtual_memory returns exactly 7 elements."""
        vmem = cygwin_cext.virtual_memory()
        assert len(vmem) == 7, f"Expected 7 elements, got {len(vmem)}"

    def test_virtual_memory_field_types(self, cygwin_cext):
        """Test that all virtual_memory fields are integers."""
        vmem = cygwin_cext.virtual_memory()
        field_names = [
            'total',
            'available',
            'used',
            'free',
            'cached',
            'buffers',
            'shared',
        ]

        for i, (name, value) in enumerate(zip(field_names, vmem)):
            assert isinstance(value, int), (
                f"Field {name} (index {i}) should be int, got"
                f" {type(value).__name__}"
            )

    def test_virtual_memory_total_positive(self, cygwin_cext):
        """Test that total memory is positive."""
        vmem = cygwin_cext.virtual_memory()
        total = vmem[0]
        assert total > 0, f"Total memory should be positive, got {total}"

    def test_virtual_memory_fields_non_negative(self, cygwin_cext):
        """Test that memory fields are non-negative."""
        vmem = cygwin_cext.virtual_memory()
        field_names = [
            'total',
            'available',
            'used',
            'free',
            'cached',
            'buffers',
            'shared',
        ]

        for i, (name, value) in enumerate(zip(field_names, vmem)):
            assert (
                value >= 0
            ), f"Field {name} should be non-negative, got {value}"

    def test_virtual_memory_available_not_exceeds_total(self, cygwin_cext):
        """Test that available memory does not exceed total memory."""
        vmem = cygwin_cext.virtual_memory()
        total, available = vmem[0], vmem[1]
        assert (
            available <= total
        ), f"Available memory ({available}) should not exceed total ({total})"

    def test_virtual_memory_reasonable_values(self, cygwin_cext):
        """Test that memory values are in reasonable ranges."""
        vmem = cygwin_cext.virtual_memory()
        total = vmem[0]

        # Total memory should be at least 64MB and less than 1TB
        min_memory = 64 * 1024 * 1024  # 64MB
        max_memory = 1024 * 1024 * 1024 * 1024  # 1TB

        assert min_memory <= total <= max_memory, (
            f"Total memory {total} bytes ({total // 1024 // 1024}MB) seems"
            " unreasonable"
        )

    def test_virtual_memory_cross_validation_with_psutil(
        self, cygwin_cext, psutil_module, system_constants
    ):
        """Test that virtual_memory values are consistent with psutil."""
        cext_vmem = cygwin_cext.virtual_memory()
        psutil_vmem = psutil_module.virtual_memory()

        cext_total = cext_vmem[0]
        psutil_total = psutil_vmem.total

        tolerance = system_constants['memory_tolerance_bytes']
        total_diff = abs(cext_total - psutil_total)

        assert total_diff <= tolerance, (
            f"Total memory difference too large: C ext {cext_total}, psutil"
            f" {psutil_total}, diff {total_diff}"
        )

    def test_virtual_memory_performance(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test that virtual_memory executes within reasonable time."""
        with performance_timer as perf:
            cygwin_cext.virtual_memory()

        assert perf.duration_ms is not None
        threshold = system_constants['performance_threshold_ms']
        assert (
            perf.duration_ms < threshold
        ), f"Function took {perf.duration_ms:.3f}ms, expected < {threshold}ms"


class TestSwapMemory:
    """Test suite for swap_memory() function."""

    def test_swap_memory_return_type(self, cygwin_cext):
        """Test that swap_memory returns a tuple."""
        swap = cygwin_cext.swap_memory()
        assert isinstance(
            swap, tuple
        ), f"Expected tuple, got {type(swap).__name__}"

    def test_swap_memory_tuple_length(self, cygwin_cext):
        """Test that swap_memory returns exactly 6 elements."""
        swap = cygwin_cext.swap_memory()
        assert len(swap) == 6, f"Expected 6 elements, got {len(swap)}"

    def test_swap_memory_field_types(self, cygwin_cext):
        """Test that swap_memory fields have correct types."""
        swap = cygwin_cext.swap_memory()
        total, used, free, percent, sin, sout = swap

        expected_types = [
            ('total', total, int),
            ('used', used, int),
            ('free', free, int),
            ('percent', percent, float),
            ('sin', sin, int),
            ('sout', sout, int),
        ]

        for name, value, expected_type in expected_types:
            assert isinstance(value, expected_type), (
                f"Field {name} should be {expected_type.__name__}, got"
                f" {type(value).__name__}"
            )

    def test_swap_memory_fields_non_negative(self, cygwin_cext):
        """Test that swap memory fields are non-negative."""
        swap = cygwin_cext.swap_memory()
        field_names = ['total', 'used', 'free', 'percent', 'sin', 'sout']

        for i, (name, value) in enumerate(zip(field_names, swap)):
            assert (
                value >= 0
            ), f"Field {name} should be non-negative, got {value}"

    def test_swap_memory_percent_range(self, cygwin_cext):
        """Test that swap percentage is in valid range 0-100."""
        swap = cygwin_cext.swap_memory()
        percent = swap[3]
        assert (
            0.0 <= percent <= 100.0
        ), f"Swap percentage should be 0-100, got {percent}"

    def test_swap_memory_mathematical_consistency(self, cygwin_cext):
        """Test mathematical consistency of swap memory values."""
        swap = cygwin_cext.swap_memory()
        total, used, free, percent = swap[:4]

        if total > 0:
            # Test that total = used + free (allow small rounding errors)
            sum_check = abs(total - (used + free))
            assert sum_check <= 1024

            # Test percentage calculation
            expected_percent = (used / total) * 100.0
            percent_diff = abs(percent - expected_percent)
            assert percent_diff <= 0.1, (
                f"Percentage calculation error: {percent} vs expected"
                f" {expected_percent:.3f}"
            )
        else:
            # If no swap, everything should be 0
            msg = (
                "With no swap space, all values should be 0"
                f" used={used}, free={free}, percent={percent}"
            )
            assert used == 0, msg
            assert free == 0, msg
            assert percent == 0.0, msg

    def test_swap_memory_cross_validation_with_psutil(
        self, cygwin_cext, psutil_module, system_constants
    ):
        """Test that swap_memory values are consistent with psutil."""
        cext_swap = cygwin_cext.swap_memory()
        psutil_swap = psutil_module.swap_memory()

        cext_total = cext_swap[0]
        psutil_total = psutil_swap.total

        if cext_total > 0:  # Only validate if swap exists
            tolerance = system_constants['memory_tolerance_bytes']
            total_diff = abs(cext_total - psutil_total)

            assert total_diff <= tolerance, (
                f"Swap total difference too large: C ext {cext_total}, psutil"
                f" {psutil_total}, diff {total_diff}"
            )

    def test_swap_memory_performance(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test that swap_memory executes within reasonable time."""
        with performance_timer as perf:
            cygwin_cext.swap_memory()

        assert perf.duration_ms is not None
        threshold = system_constants['performance_threshold_ms']
        assert (
            perf.duration_ms < threshold
        ), f"Function took {perf.duration_ms:.3f}ms, expected < {threshold}ms"

    def test_swap_memory_no_swap_handling(self, cygwin_cext):
        """Test proper handling when no swap space is available."""
        swap = cygwin_cext.swap_memory()
        total = swap[0]

        if total == 0:
            # When no swap, other values should be 0 as well
            used, free, percent, _sin, _sout = swap[1:]
            assert used == 0, f"With no swap, used should be 0, got {used}"
            assert free == 0, f"With no swap, free should be 0, got {free}"
            assert (
                percent == 0.0
            ), f"With no swap, percent should be 0.0, got {percent}"
            # sin/sout can be non-zero even with no current swap space

    @pytest.mark.parametrize("swap_size_mb", [0, 512, 1024, 2048, 4096])
    def test_swap_memory_various_sizes(self, cygwin_cext, swap_size_mb):
        """Test swap memory handling for various theoretical sizes."""
        # This is more of a structural test - we can't control actual swap size
        swap = cygwin_cext.swap_memory()
        total = swap[0]

        # Verify the structure is consistent regardless of actual swap size
        assert isinstance(total, int)
        assert total >= 0

        if total > 0:
            used, free, percent = swap[1], swap[2], swap[3]
            assert used + free == total or abs((used + free) - total) <= 1024
            assert 0.0 <= percent <= 100.0


class TestProcessMemoryInfo:
    """Test suite for process memory_info() function."""

    def test_process_memory_info_basic(self):
        """Test basic memory_info functionality via psutil API."""
        current_pid = os.getpid()
        proc = psutil.Process(current_pid)
        mem_info = proc.memory_info()

        # Should have rss and vms attributes
        assert hasattr(mem_info, 'rss')
        assert hasattr(mem_info, 'vms')

        # Both should be positive integers
        assert isinstance(mem_info.rss, int)
        assert isinstance(mem_info.vms, int)
        assert mem_info.rss > 0
        assert mem_info.vms > 0

        # VMS should generally be >= RSS
        assert mem_info.vms >= mem_info.rss

    def test_process_memory_info_reasonable_values(self):
        """Test that memory info values are in reasonable ranges."""
        current_pid = os.getpid()
        proc = psutil.Process(current_pid)
        mem_info = proc.memory_info()

        # Memory should be at least 1MB and less than 16GB for typical jobs
        min_memory = 1024 * 1024  # 1MB
        max_memory = 16 * 1024 * 1024 * 1024  # 16GB

        assert (
            min_memory <= mem_info.rss <= max_memory
        ), f"RSS {mem_info.rss} bytes seems unreasonable"
        assert (
            min_memory <= mem_info.vms <= max_memory
        ), f"VMS {mem_info.vms} bytes seems unreasonable"


class TestProcessMemoryFullInfo:
    """Test suite for process memory_full_info() function."""

    def test_proc_memory_full_info_basic(self, cygwin_cext):
        """Basic test for memory full info functionality."""
        current_pid = os.getpid()
        result = cygwin_cext.proc_memory_full_info(current_pid)

        # Should return a tuple with 10 elements
        assert isinstance(result, tuple)
        assert len(result) == 10

        rss, vms, _shared, _text, _lib, _data, _dirty, uss, _pss, _swap = (
            result
        )

        # All should be non-negative integers
        for i, value in enumerate(result):
            assert isinstance(
                value, int
            ), f"Element {i} should be int, got {type(value).__name__}"
            assert (
                value >= 0
            ), f"Element {i} should be non-negative, got {value}"

        # Basic sanity checks
        assert rss > 0, "Running process should have RSS > 0"
        assert vms > 0, "Running process should have VMS > 0"
        assert vms >= rss, f"VMS ({vms}) should be >= RSS ({rss})"
        assert uss <= rss, f"USS ({uss}) should be <= RSS ({rss})"

    def test_python_integration_memory_full_info(self):
        """Test integration with psutil.Process.memory_full_info()."""
        current_pid = os.getpid()
        proc = psutil.Process(current_pid)
        result = proc.memory_full_info()

        # Check expected attributes
        expected_attrs = ['rss', 'vms', 'uss', 'pss', 'swap']
        for attr in expected_attrs:
            assert hasattr(result, attr), f"Missing attribute: {attr}"
            value = getattr(result, attr)
            assert isinstance(value, int), f"Attribute {attr} should be int"
            assert value >= 0, f"Attribute {attr} should be non-negative"

        # Basic sanity checks
        assert result.rss > 0, "Running process should have RSS > 0"
        assert result.vms > 0, "Running process should have VMS > 0"

    def test_memory_full_info_invalid_pid_handling(self, cygwin_cext):
        """Test error handling for invalid PIDs."""
        # Test negative PID - should raise ProcessLookupError
        with pytest.raises(ProcessLookupError):
            cygwin_cext.proc_memory_full_info(-1)

        # Test non-existent PID - should raise ProcessLookupError
        with pytest.raises(ProcessLookupError):
            cygwin_cext.proc_memory_full_info(999999)


class TestProcessMemoryMaps:
    """Test suite for process memory_maps() function."""

    def test_proc_memory_maps_basic(self, cygwin_cext):
        """Basic test for memory maps functionality."""
        current_pid = os.getpid()
        result = cygwin_cext.proc_memory_maps(current_pid)

        # Should return a list
        assert isinstance(result, list)

        # Should have at least some entries for current process
        assert len(result) > 0, "Current process should have memory maps"

        # Each entry should be a tuple with 13 elements
        for i, map_entry in enumerate(result[:3]):  # Test first 3 entries
            assert isinstance(map_entry, tuple), f"Entry {i} should be tuple"
            assert len(map_entry) == 13, (
                f"Entry {i}: got {len(map_entry)} elements, expected 13."
                f" Contents: {map_entry}"
            )

            addr, perms, path = map_entry[:3]
            size = map_entry[4]

            # Basic validation
            assert isinstance(
                addr, str
            ), f"Address should be string, got {type(addr).__name__}"
            assert '-' in addr, f"Address should contain '-' separator: {addr}"
            assert isinstance(
                perms, str
            ), f"Permissions should be string, got {type(perms).__name__}"
            assert isinstance(
                path, str
            ), f"Path should be string, got {type(path).__name__}"
            assert isinstance(
                size, int
            ), f"Size should be int, got {type(size).__name__}"
            assert size > 0, f"Size should be positive, got {size}"

    def test_python_integration_memory_maps_grouped(self):
        """Test integration with psutil.Process.memory_maps() (grouped=True)"""
        current_pid = os.getpid()
        proc = psutil.Process(current_pid)
        result = proc.memory_maps()  # Default is grouped=True

        assert isinstance(result, list)

        if len(result) > 0:
            # Check first entry has expected attributes for grouped=True
            map_entry = result[0]
            # Default behavior (grouped=True) should return
            # pmmap_grouped namedtuple
            assert hasattr(
                map_entry, 'path'
            ), "Entry should have 'path' attribute"
            assert hasattr(
                map_entry, 'size'
            ), "Entry should have 'size' attribute"
            # pmmap_grouped does not have addr/perms attributes
            assert not hasattr(
                map_entry, 'addr'
            ), "Grouped entry should not have 'addr'"
            assert not hasattr(
                map_entry, 'perms'
            ), "Grouped entry should not have 'perms'"

    def test_python_integration_memory_maps_ungrouped(self):
        """Test integration with psutil.Process.memory_maps(grouped=False)."""
        current_pid = os.getpid()
        proc = psutil.Process(current_pid)
        result = proc.memory_maps(grouped=False)

        assert isinstance(result, list)

        if len(result) > 0:
            # Check first entry has expected attributes for grouped=False
            map_entry = result[0]
            # When grouped=False, should return pmmap_ext with addr and perms
            assert hasattr(
                map_entry, 'addr'
            ), "Ungrouped entry should have 'addr'"
            assert hasattr(
                map_entry, 'perms'
            ), "Ungrouped entry should have 'perms'"
            assert hasattr(
                map_entry, 'path'
            ), "Entry should have 'path' attribute"
            assert hasattr(
                map_entry, 'size'
            ), "Entry should have 'size' attribute"

    def test_memory_maps_invalid_pid_handling(self, cygwin_cext):
        """Test error handling for invalid PIDs."""
        # Test negative PID - should raise ProcessLookupError
        with pytest.raises(ProcessLookupError):
            cygwin_cext.proc_memory_maps(-1)

        # Test non-existent PID - should raise ProcessLookupError
        with pytest.raises(ProcessLookupError):
            cygwin_cext.proc_memory_maps(999999)


class TestMemoryIntegration:
    """Integration tests between different memory functions."""

    def test_memory_functions_consistency(self, cygwin_cext):
        """Test that memory functions return consistent system view."""
        vmem = cygwin_cext.virtual_memory()
        swap = cygwin_cext.swap_memory()

        # Both should execute successfully
        assert len(vmem) == 7
        assert len(swap) == 6

        # Virtual memory total should be much larger than swap total, typically
        vmem_total = vmem[0]
        swap_total = swap[0]

        if swap_total > 0:
            # Swap is typically smaller than or equal to physical memory
            assert swap_total <= vmem_total * 2, (
                f"Swap size ({swap_total}) seems too large compared to "
                f"virtual memory ({vmem_total})"
            )

    def test_memory_functions_rapid_calls(self, cygwin_cext):
        """Test that memory functions handle rapid successive calls."""
        # Call both functions multiple times rapidly
        results = []
        for i in range(5):
            vmem = cygwin_cext.virtual_memory()
            swap = cygwin_cext.swap_memory()
            results.append((vmem, swap))

        # All calls should succeed and return reasonable values
        for i, (vmem, swap) in enumerate(results):
            assert (
                len(vmem) == 7
            ), f"Call {i}: virtual_memory returned {len(vmem)} elements"
            assert (
                len(swap) == 6
            ), f"Call {i}: swap_memory returned {len(swap)} elements"
            assert (
                vmem[0] > 0
            ), f"Call {i}: total virtual memory should be positive"

    def test_system_vs_process_memory_consistency(self, cygwin_cext):
        """Test consistency between system and process memory functions."""
        current_pid = os.getpid()
        # Get system memory info
        vmem = cygwin_cext.virtual_memory()
        system_total = vmem[0]

        # Get current process memory info
        proc_mem = cygwin_cext.proc_memory_full_info(current_pid)
        proc_rss = proc_mem[0]  # RSS is first element

        # Process RSS should be much smaller than total system memory
        assert proc_rss < system_total, (
            f"Process RSS ({proc_rss}) should be less than system "
            f"total ({system_total})"
        )

        # Process RSS should be reasonable (<10% of system memory)
        max_reasonable_rss = system_total // 10
        assert proc_rss <= max_reasonable_rss, (
            f"Process RSS ({proc_rss}) seems too large compared to "
            f"system memory ({system_total})"
        )

    def test_memory_maps_vs_memory_info_consistency(self, cygwin_cext):
        """Test consistency between memory maps and memory info."""
        current_pid = os.getpid()
        # Get process memory info
        proc_mem = cygwin_cext.proc_memory_full_info(current_pid)
        vms_from_info = proc_mem[1]  # VMS is second element

        # Get memory maps
        memory_maps = cygwin_cext.proc_memory_maps(current_pid)

        # Calculate total size from memory maps
        total_mapped_size = sum(
            map_entry[4] for map_entry in memory_maps
        )  # Size is 5th element

        # Total mapped size should be related to VMS, but might not be
        # exactly equal due to differences in calculations. On Cygwin,
        # memory mapping can differ from VMS due to Windows/Unix hybrid.
        if total_mapped_size > 0 and vms_from_info > 0:
            ratio = max(total_mapped_size, vms_from_info) / min(
                total_mapped_size, vms_from_info
            )
            # Use higher tolerance for Cygwin platform differences
            max_ratio = 500  # Allow up to 500x difference on Cygwin
            assert ratio <= max_ratio, (
                f"Memory maps total ({total_mapped_size}) and VMS "
                f"({vms_from_info}) differ too much (ratio: {ratio:.1f}), "
                f"max allowed: {max_ratio}"
            )

    def test_memory_performance_comparison(
        self, cygwin_cext, system_constants, performance_timer
    ):
        """Test performance comparison between different memory functions."""
        threshold = system_constants['performance_threshold_ms']
        current_pid = os.getpid()

        # Test batch performance (calling all functions together)
        with performance_timer as perf:
            cygwin_cext.virtual_memory()
            cygwin_cext.swap_memory()
            cygwin_cext.proc_memory_full_info(current_pid)

        # Allow more time for batch operation
        batch_threshold = threshold * 3
        assert perf.duration_ms < batch_threshold, (
            f"Batch memory operations took {perf.duration_ms:.3f}ms, "
            f"expected < {batch_threshold}ms"
        )

    def test_memory_stress_test(self, cygwin_cext):
        """Stress test memory functions with multiple rapid calls."""
        current_pid = os.getpid()
        # Call all memory functions rapidly to test stability
        for i in range(20):
            try:
                vmem = cygwin_cext.virtual_memory()
                swap = cygwin_cext.swap_memory()
                proc_mem = cygwin_cext.proc_memory_full_info(current_pid)
                memory_maps = cygwin_cext.proc_memory_maps(current_pid)

                # Basic validation on each iteration
                assert len(vmem) == 7
                assert len(swap) == 6
                assert len(proc_mem) == 10
                assert isinstance(memory_maps, list)
                assert len(memory_maps) > 0

            except (OSError, RuntimeError, PermissionError) as e:
                pytest.fail(f"Memory stress test failed on iteration {i}: {e}")


class TestMemoryErrorHandling:
    """Test error handling and edge cases for memory functions."""

    def test_virtual_memory_error_resilience(self, cygwin_cext):
        """Test virtual_memory error resilience."""
        # Should not raise exceptions under normal circumstances
        for _ in range(10):
            try:
                vmem = cygwin_cext.virtual_memory()
                assert len(vmem) == 7
            except (OSError, RuntimeError, PermissionError) as e:
                pytest.fail(
                    "virtual_memory should not fail under normal"
                    f" conditions: {e}"
                )

    def test_swap_memory_error_resilience(self, cygwin_cext):
        """Test swap_memory error resilience."""
        # Should not raise exceptions under normal circumstances
        for _ in range(10):
            try:
                swap = cygwin_cext.swap_memory()
                assert len(swap) == 6
            except (OSError, RuntimeError, PermissionError) as e:
                pytest.fail(
                    f"swap_memory should not fail under normal conditions: {e}"
                )

    def test_process_memory_functions_error_handling(self, cygwin_cext):
        """Test error handling for process memory functions."""
        # Test with various invalid PIDs - all should raise ProcessLookupError
        invalid_pids = [-1, 0, 999999, -999]

        for pid in invalid_pids:
            # All invalid PIDs should raise ProcessLookupError for Cygwin
            # implementation
            with pytest.raises(ProcessLookupError):
                cygwin_cext.proc_memory_full_info(pid)
            with pytest.raises(ProcessLookupError):
                cygwin_cext.proc_memory_maps(pid)

    def test_memory_functions_thread_safety(self, cygwin_cext):
        """Test basic thread safety of memory functions (sequential test)."""
        import queue
        import threading

        results = queue.Queue()
        errors = queue.Queue()

        def worker():
            try:
                current_pid = os.getpid()
                vmem = cygwin_cext.virtual_memory()
                swap = cygwin_cext.swap_memory()
                proc_mem = cygwin_cext.proc_memory_full_info(current_pid)
                results.put((vmem, swap, proc_mem))
            except (OSError, RuntimeError, PermissionError) as e:
                errors.put(e)

        # Run multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Check for errors
        assert errors.empty(), f"Thread safety test failed: {errors.get()}"

        # Verify all results are valid
        assert results.qsize() == 5, "Not all threads completed successfully"
        while not results.empty():
            vmem, swap, proc_mem = results.get()
            assert len(vmem) == 7
            assert len(swap) == 6
            assert len(proc_mem) == 10
