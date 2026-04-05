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
