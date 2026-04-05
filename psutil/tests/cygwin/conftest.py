#!/usr/bin/env python3
# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""pytest configuration and shared fixtures for psutil Cygwin test suite.

This module provides:
- Test fixtures for C extension and psutil imports
- Configuration for pytest
- Shared utilities for test validation
- Performance measurement helpers
- Cross-validation utilities
"""

import os
import socket
import sys
import time

import pytest


class TestEnvironment:
    """Test environment validation and information."""

    @staticmethod
    def validate_cygwin():
        """Validate that we're running in a Cygwin environment."""
        return sys.platform.startswith('cygwin')

    @staticmethod
    def get_system_info():
        """Get comprehensive system information for diagnostics."""
        return {
            'python_version': sys.version,
            'python_executable': sys.executable,
            'platform': sys.platform,
            'working_directory': os.getcwd(),
            'process_id': os.getpid(),
            'is_cygwin': sys.platform.startswith('cygwin'),
            'cygwin_root': os.path.exists('/cygdrive'),
            'proc_exists': os.path.exists('/proc'),
        }


class PerformanceMeasurement:
    """Helper for measuring function call performance."""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()

    @property
    def duration_ms(self):
        """Get duration in milliseconds."""
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000


class DiagnosticReporter:
    """Enhanced diagnostic reporting for test failures."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def log_error(self, test_name, exception, context=None):
        """Log detailed error information."""
        import traceback
        from datetime import datetime

        error_info = {
            'test': test_name,
            'exception': str(exception),
            'exception_type': type(exception).__name__,
            'traceback': traceback.format_exc(),
            'timestamp': datetime.now().isoformat(),
            'context': context or {},
        }
        self.errors.append(error_info)

        # Use logging instead of print statements
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            "Test failure: %s - %s: %s",
            test_name,
            type(exception).__name__,
            exception,
        )
        if context:
            logger.error("Context: %s", context)

    def log_warning(self, test_name, message, context=None):
        """Log warning information."""
        from datetime import datetime

        warning_info = {
            'test': test_name,
            'message': message,
            'context': context or {},
            'timestamp': datetime.now().isoformat(),
        }
        self.warnings.append(warning_info)

        import logging

        logger = logging.getLogger(__name__)
        logger.warning("Warning [%s]: %s", test_name, message)
        if context:
            for key, value in context.items():
                logger.warning("  %s: %s", key, value)


@pytest.fixture(scope="session")
def test_environment():
    """Provide test environment information."""
    return TestEnvironment()


@pytest.fixture(scope="session")
def cygwin_cext():
    """Import and validate the Cygwin C extension."""
    try:
        import psutil._psutil_cygwin as cext

        return cext
    except ImportError as e:
        pytest.fail(f"Cannot import psutil._psutil_cygwin: {e}")


@pytest.fixture(scope="session")
def psutil_module():
    """Import and validate the main psutil module."""
    try:
        import psutil

        return psutil
    except ImportError as e:
        pytest.fail(f"Cannot import psutil: {e}")


@pytest.fixture
def performance_timer():
    """Provide a performance measurement context manager."""
    return PerformanceMeasurement()


@pytest.fixture
def reporter():
    """Provide a diagnostic reporter for test failures."""
    return DiagnosticReporter()


@pytest.fixture(scope="session")
def system_constants():
    """Provide system constants for validation."""
    return {
        'common_page_sizes': [
            512,
            1024,
            2048,
            4096,
            8192,
            16384,
            32768,
            65536,
        ],
        'max_reasonable_cpu_count': 1024,
        'max_reasonable_core_count': 512,
        'max_reasonable_cpu_time_seconds': 86400 * 365,  # 1 year in seconds
        'memory_tolerance_bytes': 1024 * 1024,  # 1MB tolerance
        'time_tolerance_seconds': 10.0,  # 10 second tolerance
        'performance_threshold_ms': (
            100.0
        ),  # Functions should complete within 100ms
    }


@pytest.fixture
def cross_validation_sources():
    """Provide available cross-validation sources."""
    sources = {}

    # Try to import various modules for cross-validation
    try:
        import multiprocessing

        sources['multiprocessing'] = multiprocessing
    except ImportError:
        pass

    try:
        sources['os'] = os
    except (ImportError, AttributeError):
        pass

    return sources


@pytest.fixture(scope="session")
def cext(cygwin_cext):
    """Alias for cygwin_cext fixture for backward compatibility."""
    return cygwin_cext


@pytest.fixture
def network_test_socket():
    """Provide a test socket for network function validation."""
    test_socket = None
    try:
        # Create a simple test socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.bind(('127.0.0.1', 0))  # Bind to any available port
        test_socket.listen(1)

        # Get the actual port
        port = test_socket.getsockname()[1]

        yield {
            'socket': test_socket,
            'address': '127.0.0.1',
            'port': port,
            'family': socket.AF_INET,
            'type': socket.SOCK_STREAM,
        }
    finally:
        if test_socket:
            try:
                test_socket.close()
            except OSError:
                pass


# Connection status constants for tests
@pytest.fixture(scope="session")
def connection_states():
    """Provide connection state constants."""
    return {
        'ESTABLISHED': 1,
        'SYN_SENT': 2,
        'SYN_RECV': 3,
        'FIN_WAIT1': 4,
        'FIN_WAIT2': 5,
        'TIME_WAIT': 6,
        'CLOSE': 7,
        'CLOSE_WAIT': 8,
        'LAST_ACK': 9,
        'LISTEN': 10,
        'CLOSING': 11,
        'NONE': 0,
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "unit: mark test as unit test")
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "cross_validation: mark test as cross-validation test"
    )
    config.addinivalue_line(
        "markers", "network: mark test as network-related test"
    )
    config.addinivalue_line("markers", "cpu: mark test as CPU-related test")
    config.addinivalue_line(
        "markers", "memory: mark test as memory-related test"
    )
    config.addinivalue_line(
        "markers", "process: mark test as process-related test"
    )
    config.addinivalue_line("markers", "disk: mark test as disk-related test")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add markers based on test name patterns
        test_name_lower = item.name.lower()

        if "integration" in test_name_lower:
            item.add_marker(pytest.mark.integration)
        elif "performance" in test_name_lower:
            item.add_marker(pytest.mark.performance)
        elif "cross_validation" in test_name_lower:
            item.add_marker(pytest.mark.cross_validation)
        else:
            item.add_marker(pytest.mark.unit)

        # Add functional area markers
        if "network" in test_name_lower or "net_" in test_name_lower:
            item.add_marker(pytest.mark.network)
        if "cpu" in test_name_lower:
            item.add_marker(pytest.mark.cpu)
        if "memory" in test_name_lower or "mem" in test_name_lower:
            item.add_marker(pytest.mark.memory)
        if "process" in test_name_lower or "proc" in test_name_lower:
            item.add_marker(pytest.mark.process)
        if "disk" in test_name_lower:
            item.add_marker(pytest.mark.disk)


def pytest_sessionstart(session):
    """Display information at the start of test session."""
    env = TestEnvironment()
    info = env.get_system_info()

    import logging

    logger = logging.getLogger(__name__)

    logger.info("=" * 80)
    logger.info("PSUTIL CYGWIN TEST SUITE")
    logger.info("=" * 80)
    logger.info("Python: %s", info['python_version'].split()[0])
    logger.info("Platform: %s", info['platform'])
    logger.info("Cygwin Environment: %s", '✓' if info['is_cygwin'] else '✗')
    logger.info("/proc exists: %s", '✓' if info['proc_exists'] else '✗')
    logger.info("/cygdrive exists: %s", '✓' if info['cygwin_root'] else '✗')
    logger.info("Working Directory: %s", info['working_directory'])
    logger.info("=" * 80)
