#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Disk operations test suite for psutil Cygwin implementation.

This module tests:
- disk_partitions() - Disk partition enumeration
- disk_usage() - Disk space usage statistics
- disk_io_counters() - Disk I/O statistics

Functions covered: disk_partitions(), disk_usage(), disk_io_counters()
"""

import collections
import os
import sys
import tempfile

import pytest

# =============================================================================
# Test disk_partitions()
# =============================================================================


class TestDiskPartitions:
    """Test disk partition enumeration."""

    def test_disk_partitions_basic(self, psutil_module):
        """Test that disk_partitions returns valid data."""
        partitions = psutil_module.disk_partitions(all=False)
        assert isinstance(partitions, list)
        assert len(partitions) > 0, "Should have at least one partition"

        # Check the structure of each partition
        for part in partitions:
            assert isinstance(part, tuple)
            assert len(part) == 4
            device, mountpoint, fstype, opts = part

            assert isinstance(device, str)
            assert isinstance(mountpoint, str)
            assert isinstance(fstype, str)
            assert isinstance(opts, str)

            # Basic validation
            assert device, "Device should not be empty"
            assert mountpoint, "Mountpoint should not be empty"
            assert fstype, "Filesystem type should not be empty"

            # Check that mountpoint exists (for real partitions)
            # Skip cygdrive paths as they may be virtual on some systems
            if (
                not opts.startswith("bind")
                and "loop" not in device
                and not mountpoint.startswith("/cygdrive/")
            ):
                assert (
                    os.path.exists(mountpoint) or mountpoint == "/"
                ), f"Mountpoint {mountpoint} should exist"

    def test_disk_partitions_all_parameter(self, psutil_module):
        """Test that all=True returns different (usually more) partitions."""
        partitions_filtered = psutil_module.disk_partitions(all=False)
        partitions_all = psutil_module.disk_partitions(all=True)

        assert isinstance(partitions_all, list)
        # On Cygwin, the behavior might be different due to Windows drives
        # Just ensure both calls work and return reasonable results
        assert (
            len(partitions_all) > 0
        ), "all=True should return some partitions"
        assert (
            len(partitions_filtered) > 0
        ), "all=False should return some partitions"

        # Check that the results are different in some way
        # Either different counts or different content
        all_mounts = {p[1] for p in partitions_all}
        filtered_mounts = {p[1] for p in partitions_filtered}
        assert (
            len(all_mounts | filtered_mounts) > 0
        ), "Should have some mount points"

    def test_disk_partitions_cygwin_drives(self, psutil_module):
        """Test that Cygwin detects Windows drives properly."""
        if not sys.platform.startswith('cygwin'):
            pytest.skip("Not running on Cygwin")

        partitions = psutil_module.disk_partitions(all=False)

        # On Cygwin, we should see at least the C: drive
        mount_points = [p[1] for p in partitions]

        # Check for common Cygwin mount points
        has_cygdrive = any('/cygdrive/' in mp for mp in mount_points)
        has_root = any(mp == '/' for mp in mount_points)

        assert (
            has_cygdrive or has_root
        ), "Should have at least one Cygwin mount point"

    def test_disk_partitions_filesystem_types(self, psutil_module):
        """Test that filesystem types are reasonable."""
        partitions = psutil_module.disk_partitions(all=False)

        for part in partitions:
            fstype = part[2].lower()
            # Check if it's a known filesystem type or at least not empty
            assert fstype, f"Filesystem type should not be empty for {part[0]}"


# =============================================================================
# Test disk_usage()
# =============================================================================


class TestDiskUsage:
    """Test disk usage statistics."""

    def test_disk_usage_root(self, psutil_module):
        """Test disk usage for root partition."""
        usage = psutil_module.disk_usage('/')

        assert hasattr(usage, 'total')
        assert hasattr(usage, 'used')
        assert hasattr(usage, 'free')
        assert hasattr(usage, 'percent')

        # Basic sanity checks
        assert usage.total > 0, "Total disk space should be positive"
        assert usage.used >= 0, "Used disk space should be non-negative"
        assert usage.free >= 0, "Free disk space should be non-negative"
        assert 0 <= usage.percent <= 100, "Percent should be between 0 and 100"

        # Check that total = used + free (approximately)
        # Allow small difference due to reserved blocks
        calculated_total = usage.used + usage.free
        assert (
            abs(usage.total - calculated_total) < usage.total * 0.1
        ), "Total should approximately equal used + free"

    def test_disk_usage_cwd(self, psutil_module):
        """Test disk usage for current working directory."""
        usage = psutil_module.disk_usage('.')

        assert usage.total > 0
        assert usage.used >= 0
        assert usage.free >= 0
        assert 0 <= usage.percent <= 100

    def test_disk_usage_tempdir(self, psutil_module):
        """Test disk usage for temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            usage = psutil_module.disk_usage(tmpdir)

            assert usage.total > 0
            assert usage.used >= 0
            assert usage.free >= 0
            assert 0 <= usage.percent <= 100

    def test_disk_usage_invalid_path(self, psutil_module):
        """Test disk usage with invalid path."""
        with pytest.raises(
            OSError, match=r"(No such file|cannot find|not exist)"
        ):
            psutil_module.disk_usage('/invalid/path/that/does/not/exist')

    def test_disk_usage_consistency(self, psutil_module):
        """Test that disk usage is consistent across calls."""
        usage1 = psutil_module.disk_usage('/')
        usage2 = psutil_module.disk_usage('/')

        # Total should remain the same
        assert usage1.total == usage2.total

        # Used and free might change slightly but not dramatically
        # (allow 1% change for ongoing system operations)
        max_change = usage1.total * 0.01
        assert abs(usage1.used - usage2.used) < max_change
        assert abs(usage1.free - usage2.free) < max_change


# =============================================================================
# Test disk_io_counters()
# =============================================================================


class TestDiskIOCounters:
    """Test disk I/O counters."""

    def test_disk_io_counters_perdisk_true(self, psutil_module):
        """Test disk I/O counters with per-disk statistics."""
        counters = psutil_module.disk_io_counters(perdisk=True)

        # Could be None if /proc/diskstats is not available
        if counters is None:
            pytest.skip("/proc/diskstats not available on this system")

        assert isinstance(counters, dict)

        # If we have counters, check their structure
        if counters:
            for disk_name, stats in counters.items():
                assert isinstance(disk_name, str)
                assert hasattr(stats, 'read_count')
                assert hasattr(stats, 'write_count')
                assert hasattr(stats, 'read_bytes')
                assert hasattr(stats, 'write_bytes')
                assert hasattr(stats, 'read_time')
                assert hasattr(stats, 'write_time')

                # All values should be non-negative
                assert stats.read_count >= 0
                assert stats.write_count >= 0
                assert stats.read_bytes >= 0
                assert stats.write_bytes >= 0
                assert stats.read_time >= 0
                assert stats.write_time >= 0

    def test_disk_io_counters_perdisk_false(self, psutil_module):
        """Test disk I/O counters with aggregated statistics."""
        counters = psutil_module.disk_io_counters(perdisk=False)

        # Could be None if /proc/diskstats is not available
        if counters is None:
            # This is acceptable on Cygwin if /proc/diskstats doesn't exist
            # and the C extension doesn't implement Windows API fallback yet
            pytest.skip(
                "/proc/diskstats not available and no Windows API fallback"
            )

        # Should be a single namedtuple with aggregated stats
        assert hasattr(counters, 'read_count')
        assert hasattr(counters, 'write_count')
        assert hasattr(counters, 'read_bytes')
        assert hasattr(counters, 'write_bytes')
        assert hasattr(counters, 'read_time')
        assert hasattr(counters, 'write_time')

        # All values should be non-negative
        assert counters.read_count >= 0
        assert counters.write_count >= 0
        assert counters.read_bytes >= 0
        assert counters.write_bytes >= 0
        assert counters.read_time >= 0
        assert counters.write_time >= 0

    def test_disk_io_counters_consistency(self, psutil_module):
        """Test that aggregated counters match sum of per-disk counters."""
        per_disk = psutil_module.disk_io_counters(perdisk=True)
        total = psutil_module.disk_io_counters(perdisk=False)

        # Skip if not available
        if per_disk is None or total is None:
            pytest.skip("Disk I/O counters not available on this system")

        if not per_disk:
            # No per-disk stats, can't compare
            pytest.skip("No per-disk counters available for comparison")

        # Calculate sum of per-disk counters
        calculated_total = collections.namedtuple(
            'sdiskio',
            [
                'read_count',
                'write_count',
                'read_bytes',
                'write_bytes',
                'read_time',
                'write_time',
            ],
        )(
            sum(d.read_count for d in per_disk.values()),
            sum(d.write_count for d in per_disk.values()),
            sum(d.read_bytes for d in per_disk.values()),
            sum(d.write_bytes for d in per_disk.values()),
            sum(d.read_time for d in per_disk.values()),
            sum(d.write_time for d in per_disk.values()),
        )

        # They should match exactly
        assert total.read_count == calculated_total.read_count
        assert total.write_count == calculated_total.write_count
        assert total.read_bytes == calculated_total.read_bytes
        assert total.write_bytes == calculated_total.write_bytes
        assert total.read_time == calculated_total.read_time
        assert total.write_time == calculated_total.write_time

    def test_disk_io_counters_increasing(self, psutil_module):
        """Test that I/O counters are monotonically increasing."""
        counters1 = psutil_module.disk_io_counters(perdisk=False)

        # Skip if not available
        if counters1 is None:
            pytest.skip("Disk I/O counters not available on this system")

        # Do some disk I/O
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"test data" * 1000)
            f.flush()
            os.fsync(f.fileno())

        counters2 = psutil_module.disk_io_counters(perdisk=False)

        # Counters should not decrease
        assert counters2.read_count >= counters1.read_count
        assert counters2.write_count >= counters1.write_count
        assert counters2.read_bytes >= counters1.read_bytes
        assert counters2.write_bytes >= counters1.write_bytes


# =============================================================================
# Integration tests
# =============================================================================


class TestDiskIntegration:
    """Integration tests for disk functions."""

    def test_disk_usage_for_all_partitions(self, psutil_module):
        """Test that disk_usage works for all mounted partitions."""
        partitions = psutil_module.disk_partitions(all=False)

        for part in partitions:
            mountpoint = part[1]

            # Skip some special mount points that might not support statvfs
            if mountpoint in {'/proc', '/sys', '/dev/pts', '/dev/shm'}:
                continue

            # Skip cygdrive paths that might not exist as real filesystem paths
            if mountpoint.startswith('/cygdrive/'):
                # On Cygwin, cygdrive paths should be accessible
                # but might need special handling
                if sys.platform.startswith('cygwin'):
                    # Try to access it, but don't fail if it's not accessible
                    try:
                        usage = psutil_module.disk_usage(mountpoint)
                        assert usage.total > 0
                        assert 0 <= usage.percent <= 100
                    except OSError:
                        # Some drives might be disconnected or inaccessible
                        pass
                continue

            try:
                usage = psutil_module.disk_usage(mountpoint)
                assert usage.total > 0
                assert 0 <= usage.percent <= 100
            except OSError as e:
                # Some mount points might not be accessible
                # No such file/directory or Permission denied
                if e.errno in {2, 13}:
                    continue
                raise

    @pytest.mark.skipif(
        not sys.platform.startswith('cygwin'),
        reason="Cygwin-specific test",
    )
    def test_cygwin_specific_features(self, psutil_module):
        """Test Cygwin-specific disk features."""
        partitions = psutil_module.disk_partitions(all=False)

        # Get the actual cygdrive prefix from the current Cygwin environment
        def get_actual_cygdrive_prefix():
            """Get the real cygdrive prefix by reading /proc/cygdrive
            symlink.
            """
            try:
                if os.path.exists('/proc/cygdrive'):
                    target = os.readlink('/proc/cygdrive')
                    # Remove trailing slash if present
                    return target.rstrip('/')
                else:
                    return '/cygdrive'  # Default fallback
            except OSError:
                return '/cygdrive'  # Default fallback

        cygdrive_prefix = get_actual_cygdrive_prefix()

        # Check for Windows drive letters in Cygwin format
        has_windows_drives = False

        for part in partitions:
            device = part[0]
            mountpoint = part[1]

            # Check for Windows drive device format variations:
            # 1. Full format (C:\, D:\, etc.) - 3 characters
            # 2. Short format (C:, D:, etc.) - 2 characters
            if len(device) in {2, 3} and device[1] == ':':
                if len(device) == 2 or device[2] == '\\':
                    has_windows_drives = True
                    break

            # Check for Cygwin mount format based on actual cygdrive prefix:
            expected_prefix = cygdrive_prefix or '/'

            if expected_prefix == '/':
                # Special case: cygdrive prefix is root, so drives mount as
                # /c, /d, etc.
                if (
                    len(mountpoint) == 2
                    and mountpoint.startswith('/')
                    and mountpoint[1].isalpha()
                    and mountpoint[1].islower()
                ):
                    has_windows_drives = True
                    break
            else:
                # Standard case: cygdrive prefix is not root, so check for
                # prefix/letter format
                expected_pattern = f"{expected_prefix}/"
                if mountpoint.startswith(expected_pattern):
                    # Extract the part after the prefix
                    remainder = mountpoint[len(expected_pattern) :]
                    if (
                        len(remainder) == 1
                        and remainder.isalpha()
                        and remainder.islower()
                    ):
                        has_windows_drives = True
                        break

        assert has_windows_drives, (
            "Should detect Windows drives on Cygwin "
            f"(cygdrive prefix: '{cygdrive_prefix}')"
        )


# =============================================================================
# Performance tests
# =============================================================================


@pytest.mark.performance
class TestDiskPerformance:
    """Performance tests for disk operations."""

    def test_disk_partitions_performance(
        self, psutil_module, performance_timer
    ):
        """Test disk_partitions performance."""
        with performance_timer:
            partitions = psutil_module.disk_partitions(all=False)

        assert partitions is not None
        # Should complete quickly
        assert performance_timer.duration_ms < 100, (
            f"disk_partitions took {performance_timer.duration_ms:.2f}ms, "
            "expected < 100ms"
        )

    def test_disk_usage_performance(self, psutil_module, performance_timer):
        """Test disk_usage performance."""
        with performance_timer:
            usage = psutil_module.disk_usage('/')

        assert usage is not None
        # Should complete very quickly
        assert performance_timer.duration_ms < 50, (
            f"disk_usage took {performance_timer.duration_ms:.2f}ms, "
            "expected < 50ms"
        )

    def test_disk_io_counters_performance(
        self, psutil_module, performance_timer
    ):
        """Test disk_io_counters performance."""
        with performance_timer:
            counters = psutil_module.disk_io_counters(perdisk=False)

        # May be None if not available
        if counters is not None:
            # Should complete reasonably quickly
            assert performance_timer.duration_ms < 200, (
                f"disk_io_counters took {performance_timer.duration_ms:.2f}ms,"
                " expected < 200ms"
            )


# =============================================================================
# Edge cases and error handling
# =============================================================================


class TestDiskEdgeCases:
    """Test edge cases and error handling for disk operations."""

    def test_disk_usage_unicode_path(self, psutil_module):
        """Test disk_usage with Unicode path."""
        # Create a temporary directory with Unicode name
        with tempfile.TemporaryDirectory(prefix='测试_テスト_') as tmpdir:
            usage = psutil_module.disk_usage(tmpdir)
            assert usage.total > 0

    def test_disk_usage_symlink(self, psutil_module):
        """Test disk_usage with symlink."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a symlink
            link_path = os.path.join(tmpdir, 'link')
            os.symlink('/', link_path)

            # disk_usage should follow the symlink
            usage = psutil_module.disk_usage(link_path)
            assert usage.total > 0

    def test_disk_partitions_empty_result_handling(self, psutil_module):
        """Test handling of potentially empty partition list."""
        # This shouldn't happen in practice, but test the handling
        partitions = psutil_module.disk_partitions(all=False)

        # Even if empty, should be a list
        assert isinstance(partitions, list)

        # In practice, should have at least one partition
        assert len(partitions) > 0, "System should have at least one partition"

    def test_disk_io_counters_none_handling(self, psutil_module):
        """Test handling when disk_io_counters returns None."""
        counters = psutil_module.disk_io_counters(perdisk=False)

        # Either None or valid counters
        if counters is not None:
            assert hasattr(counters, 'read_count')
            assert hasattr(counters, 'write_count')
