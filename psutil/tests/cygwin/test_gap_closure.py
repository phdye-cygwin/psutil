"""Tests for Cygwin port gap closure (Tier 1-3).

Each test class corresponds to a task in the implementation plan.
"""

import os
import signal
import subprocess
import time

import psutil
import pytest
from psutil._common import STATUS_RUNNING
from psutil._common import STATUS_SLEEPING
from psutil._common import STATUS_STOPPED
from psutil._common import STATUS_ZOMBIE


# ===================================================================
# T1: Process.status() returns string
# ===================================================================


class TestT1ProcessStatus:
    """Process.status() must return a STATUS_* string, not a raw int."""

    @pytest.fixture
    def current(self):
        return psutil.Process()

    def test_returns_string(self, current):
        result = current.status()
        assert isinstance(result, str), (
            f"status() returned {type(result).__name__}, expected str"
        )

    def test_is_known_constant(self, current):
        valid = {
            psutil.STATUS_RUNNING,
            psutil.STATUS_SLEEPING,
            psutil.STATUS_DISK_SLEEP,
            psutil.STATUS_STOPPED,
            psutil.STATUS_ZOMBIE,
            psutil.STATUS_DEAD,
            psutil.STATUS_IDLE,
            psutil.STATUS_WAITING,
            psutil.STATUS_TRACING_STOP,
            psutil.STATUS_WAKING,
        }
        result = current.status()
        assert result in valid or result == '?', (
            f"status() returned {result!r}, not a known STATUS_* constant"
        )

    def test_running_or_sleeping(self, current):
        """Current process should be running or sleeping."""
        result = current.status()
        assert result in (STATUS_RUNNING, STATUS_SLEEPING)

    def test_stopped_process(self):
        """A stopped process should report STATUS_STOPPED."""
        child = subprocess.Popen(['sleep', '60'])
        try:
            time.sleep(0.3)
            os.kill(child.pid, signal.SIGSTOP)
            time.sleep(0.3)
            p = psutil.Process(child.pid)
            assert p.status() == STATUS_STOPPED
        finally:
            os.kill(child.pid, signal.SIGCONT)
            child.terminate()
            child.wait(timeout=5)

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).status()


# ===================================================================
# T2: memory_percent() — pfullmem namedtuple
# ===================================================================


class TestT2MemoryPercent:
    """memory_percent() must work — requires pfullmem at module scope."""

    def test_pfullmem_at_module_scope(self):
        assert hasattr(psutil._pscygwin, 'pfullmem'), (
            "pfullmem must be defined at module scope in _pscygwin"
        )

    def test_pfullmem_fields(self):
        expected = [
            'rss', 'vms', 'shared', 'text', 'lib', 'data', 'dirty',
            'uss', 'pss', 'swap',
        ]
        assert list(psutil._pscygwin.pfullmem._fields) == expected

    def test_memory_percent_returns_float(self):
        result = psutil.Process().memory_percent()
        assert isinstance(result, float)
        assert 0 <= result <= 100

    def test_memory_percent_memtype_rss(self):
        result = psutil.Process().memory_percent(memtype='rss')
        assert isinstance(result, float)
        assert 0 <= result <= 100

    def test_memory_percent_memtype_vms(self):
        result = psutil.Process().memory_percent(memtype='vms')
        assert isinstance(result, float)


# ===================================================================
# T3: Process.num_threads() returns >= 1
# ===================================================================


class TestT3NumThreads:
    """num_threads() must return a positive int, not 0."""

    def test_current_process_positive(self):
        assert psutil.Process().num_threads() >= 1

    def test_matches_threads_len(self):
        p = psutil.Process()
        assert p.num_threads() == len(p.threads())

    def test_child_process(self):
        child = subprocess.Popen(['sleep', '60'])
        try:
            time.sleep(0.3)
            p = psutil.Process(child.pid)
            assert p.num_threads() >= 1
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).num_threads()


# ===================================================================
# T4: net_if_stats() — own implementation
# ===================================================================


class TestT4NetIfStats:
    """net_if_stats() must not delegate to _psposix."""

    def test_returns_dict(self):
        result = psutil.net_if_stats()
        assert isinstance(result, dict)

    def test_non_empty(self):
        assert len(psutil.net_if_stats()) >= 1

    def test_values_are_snicstats(self):
        for name, stats in psutil.net_if_stats().items():
            assert hasattr(stats, 'isup'), f"{name}: missing isup"
            assert hasattr(stats, 'duplex'), f"{name}: missing duplex"
            assert hasattr(stats, 'speed'), f"{name}: missing speed"
            assert hasattr(stats, 'mtu'), f"{name}: missing mtu"

    def test_isup_is_bool(self):
        for name, stats in psutil.net_if_stats().items():
            assert isinstance(stats.isup, bool), (
                f"{name}: isup is {type(stats.isup).__name__}"
            )

    def test_mtu_positive(self):
        stats = psutil.net_if_stats()
        has_positive = any(s.mtu > 0 for s in stats.values())
        assert has_positive, "no interface has mtu > 0"


# ===================================================================
# T5: net_io_counters() — own implementation
# ===================================================================


class TestT5NetIoCounters:
    """net_io_counters() must not delegate to _psposix."""

    def test_returns_snetio(self):
        result = psutil.net_io_counters()
        assert result is not None
        assert hasattr(result, 'bytes_sent')
        assert hasattr(result, 'bytes_recv')

    def test_values_non_negative(self):
        result = psutil.net_io_counters()
        assert result.bytes_sent >= 0
        assert result.bytes_recv >= 0
        assert result.packets_sent >= 0
        assert result.packets_recv >= 0

    def test_has_traffic(self):
        result = psutil.net_io_counters()
        assert result.bytes_sent + result.bytes_recv > 0

    def test_pernic_returns_dict(self):
        result = psutil.net_io_counters(pernic=True)
        assert isinstance(result, dict)

    def test_callable_twice(self):
        psutil.net_io_counters()
        psutil.net_io_counters()


# ===================================================================
# T6: cpu_stats() — parse /proc/stat
# ===================================================================


class TestT6CpuStats:
    """cpu_stats() must return real data, not all zeros."""

    def test_returns_scpustats(self):
        result = psutil.cpu_stats()
        assert hasattr(result, 'ctx_switches')
        assert hasattr(result, 'interrupts')
        assert hasattr(result, 'soft_interrupts')
        assert hasattr(result, 'syscalls')

    def test_ctx_switches_positive(self):
        assert psutil.cpu_stats().ctx_switches > 0

    def test_interrupts_non_negative(self):
        assert psutil.cpu_stats().interrupts >= 0

    def test_all_fields_are_int(self):
        for field in psutil.cpu_stats()._fields:
            val = getattr(psutil.cpu_stats(), field)
            assert isinstance(val, int), (
                f"{field} is {type(val).__name__}"
            )

    def test_not_all_zeros(self):
        s = psutil.cpu_stats()
        assert s.ctx_switches + s.interrupts > 0


# ===================================================================
# T7: Process.environ()
# ===================================================================


class TestT7Environ:
    """Process.environ() must return a dict from /proc/[pid]/environ."""

    def test_returns_dict(self):
        result = psutil.Process().environ()
        assert isinstance(result, dict)

    def test_contains_path(self):
        assert 'PATH' in psutil.Process().environ()

    def test_keys_and_values_are_strings(self):
        env = psutil.Process().environ()
        for k, v in env.items():
            assert isinstance(k, str), f"key {k!r} not str"
            assert isinstance(v, str), f"value for {k} not str"

    def test_child_inherits_env(self):
        import uuid
        marker = f"PSUTIL_TEST_{uuid.uuid4().hex[:8]}"
        env = os.environ.copy()
        env[marker] = "hello"
        child = subprocess.Popen(
            ['sleep', '60'], env=env,
        )
        try:
            time.sleep(0.5)
            p = psutil.Process(child.pid)
            child_env = p.environ()
            assert child_env.get(marker) == "hello"
        finally:
            child.terminate()
            child.wait(timeout=5)

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).environ()


# ===================================================================
# T8: Process.terminal() — document intentional None
# ===================================================================


class TestT8Terminal:
    """Process.terminal() returns None — documented, not a stub."""

    def test_no_crash(self):
        result = psutil.Process().terminal()
        assert result is None or isinstance(result, str)

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).terminal()


# ===================================================================
# T9: Process.rlimit()
# ===================================================================


class TestT9Rlimit:
    """Process.rlimit() via POSIX getrlimit/setrlimit."""

    def test_get_nofile(self):
        result = psutil.Process().rlimit(psutil.RLIMIT_NOFILE)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_values_are_ints(self):
        soft, hard = psutil.Process().rlimit(psutil.RLIMIT_NOFILE)
        assert isinstance(soft, int)
        assert isinstance(hard, int)

    def test_soft_le_hard(self):
        soft, hard = psutil.Process().rlimit(psutil.RLIMIT_NOFILE)
        assert soft <= hard

    def test_other_pid_raises(self):
        # rlimit only works for current process on Cygwin
        for pid in psutil.pids():
            if pid != os.getpid() and pid > 1:
                with pytest.raises(psutil.AccessDenied):
                    psutil.Process(pid).rlimit(psutil.RLIMIT_NOFILE)
                break

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).rlimit(psutil.RLIMIT_NOFILE)


# ===================================================================
# T10: Process.cpu_affinity()
# ===================================================================


class TestT10CpuAffinity:
    """Process.cpu_affinity() via Win32 Get/SetProcessAffinityMask."""

    def test_returns_list(self):
        result = psutil.Process().cpu_affinity()
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_valid_cpu_indices(self):
        cpus = psutil.Process().cpu_affinity()
        ncpus = psutil.cpu_count()
        for c in cpus:
            assert 0 <= c < ncpus, f"CPU {c} out of range [0, {ncpus})"

    def test_set_and_get(self):
        p = psutil.Process()
        original = p.cpu_affinity()
        try:
            p.cpu_affinity([0])
            assert 0 in p.cpu_affinity()
        finally:
            p.cpu_affinity(original)

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).cpu_affinity()


# ===================================================================
# T11: Process.ionice()
# ===================================================================


class TestT11Ionice:
    """Process.ionice() via Win32 NtQueryInformationProcess."""

    def test_get_returns_int(self):
        result = psutil.Process().ionice()
        assert isinstance(result, int)

    def test_value_in_range(self):
        result = psutil.Process().ionice()
        assert 0 <= result <= 4, f"ionice={result} not in [0,4]"

    def test_nonexistent_pid(self):
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(999999).ionice()
