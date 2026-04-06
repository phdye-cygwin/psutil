#!/usr/bin/env python3

# Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Cygwin platform implementation.

Uses Cygwin's /proc filesystem, Windows APIs via w32api (GCC-compiled),
and POSIX APIs. WinSock is avoided — all networking uses POSIX sockets
or Win32 GetExtendedTcpTable/GetIfTable via ctypes.
"""

import functools
import getpass
import os
import socket
import subprocess
import time
from collections import namedtuple

from . import _psposix
from ._common import AccessDenied
from ._common import NoSuchProcess
from ._common import ZombieProcess
from ._common import conn_to_ntuple
from ._common import sockfam_to_enum
from ._common import socktype_to_enum

# Import the C extension - this is REQUIRED for Cygwin support
try:
    import psutil._psutil_cygwin as cext
except ImportError as e:
    # Don't create a complex fallback - just raise a clear error
    raise ImportError(
        "Cygwin C extension '_psutil_cygwin' could not be imported. "
        "This likely means:\n"
        "1. The C extension was not built - run 'python setup.py build_ext "
        "--inplace'\n"
        "2. Build failed due to missing dependencies "
        "(gcc, python3-dev, etc.)\n"
        "3. Cygwin environment is not properly configured\n"
        "Original error: "
        + str(e)
    ) from e

# Export RLIMIT constants for __init__.py (it falls back to _psplatform
# when _psutil_posix is unavailable).
import resource as _resource

RLIM_INFINITY = _resource.RLIM_INFINITY
RLIMIT_AS = _resource.RLIMIT_AS
RLIMIT_CORE = _resource.RLIMIT_CORE
RLIMIT_CPU = _resource.RLIMIT_CPU
RLIMIT_DATA = _resource.RLIMIT_DATA
RLIMIT_FSIZE = _resource.RLIMIT_FSIZE
RLIMIT_NOFILE = _resource.RLIMIT_NOFILE
RLIMIT_STACK = _resource.RLIMIT_STACK

# POSIX I/O priority classes (same values as Linux ioprio_get/set)
IOPRIO_CLASS_NONE = 0
IOPRIO_CLASS_RT = 1
IOPRIO_CLASS_BE = 2
IOPRIO_CLASS_IDLE = 3

# Win32 priority → POSIX (class, value) for ionice_get
_WIN32_TO_IOCLASS = {
    0: (IOPRIO_CLASS_IDLE, 0),
    1: (IOPRIO_CLASS_BE, 7),
    2: (IOPRIO_CLASS_NONE, 0),
    3: (IOPRIO_CLASS_RT, 0),
}

__extra__all__ = [
    "IOPRIO_CLASS_NONE", "IOPRIO_CLASS_RT",
    "IOPRIO_CLASS_BE", "IOPRIO_CLASS_IDLE",
]

# =====================================================================
# --- namedtuples
# =====================================================================

# Define namedtuples for Cygwin - these match the definitions in _common.py
# but we define them locally to avoid import issues
svmem = namedtuple('svmem', ['total', 'available', 'percent', 'used', 'free'])
pmem = namedtuple(
    'pmem', ['rss', 'vms', 'shared', 'text', 'lib', 'data', 'dirty']
)
pcputimes = namedtuple(
    'pcputimes', ['user', 'system', 'children_user', 'children_system']
)
pthread = namedtuple('pthread', ['id', 'user_time', 'system_time'])
pctxsw = namedtuple('pctxsw', ['voluntary', 'involuntary'])
pio = namedtuple(
    'pio', ['read_count', 'write_count', 'read_bytes', 'write_bytes']
)
puids = namedtuple('puids', ['real', 'effective', 'saved'])
pgids = namedtuple('pgids', ['real', 'effective', 'saved'])
from ._common import popenfile as pfile
sswap = namedtuple(
    'sswap', ['total', 'used', 'free', 'percent', 'sin', 'sout']
)
scpustats = namedtuple(
    'scpustats', ['ctx_switches', 'interrupts', 'soft_interrupts', 'syscalls']
)
pfullmem = namedtuple(
    'pfullmem', ['rss', 'vms', 'shared', 'text', 'lib', 'data', 'dirty',
                 'uss', 'pss', 'swap']
)

# Memory maps namedtuples for process memory mapping
pmmap_grouped = namedtuple(
    'pmmap_grouped',
    [
        'path',
        'rss',
        'size',
        'pss',
        'shared_clean',
        'shared_dirty',
        'private_clean',
        'private_dirty',
        'referenced',
        'anonymous',
        'swap',
    ],
)
pmmap_ext = namedtuple(
    'pmmap_ext',
    [
        'addr',
        'perms',
        'path',
        'rss',
        'size',
        'pss',
        'shared_clean',
        'shared_dirty',
        'private_clean',
        'private_dirty',
        'referenced',
        'anonymous',
        'swap',
    ],
)

# CPU times namedtuple for per_cpu_times - 10 fields to match other platforms
scputimes_per_cpu = namedtuple(
    'scputimes',
    [
        'user',
        'nice',
        'system',
        'idle',
        'iowait',
        'irq',
        'softirq',
        'steal',
        'guest',
        'guest_nice',
    ],
)

from ._common import sdiskpart
from ._common import sdiskusage

# =====================================================================
# --- globals
# =====================================================================

HAS_PROC_IO_COUNTERS = True
HAS_NET_IO_COUNTERS = True
HAS_THREADS = True
AF_LINK = None  # Not available on Cygwin

# Process status mapping from C extension integer codes to psutil constants.
# These codes are defined in arch/cygwin/proc.c psutil_proc_status():
#   0 = running, 1 = sleeping (TTY I/O wait), 5 = stopped, 8 = zombie/exited
from ._common import STATUS_DEAD
from ._common import STATUS_RUNNING
from ._common import STATUS_SLEEPING
from ._common import STATUS_STOPPED
from ._common import STATUS_ZOMBIE

PROC_STATUSES = {
    0: STATUS_RUNNING,
    1: STATUS_SLEEPING,
    5: STATUS_STOPPED,
    8: STATUS_ZOMBIE,
}

# Letter-based status from /proc/[pid]/stat field 3 (same as Linux)
PROC_STATUSES_LETTER = {
    "R": STATUS_RUNNING,
    "S": STATUS_SLEEPING,
    "D": STATUS_SLEEPING,  # disk sleep → sleeping on Cygwin
    "T": STATUS_STOPPED,
    "Z": STATUS_ZOMBIE,
    "X": STATUS_DEAD,
    "x": STATUS_DEAD,
}

# Connection status mapping from Windows constants to psutil constants
TCP_STATUSES = {
    1: "ESTABLISHED",
    2: "SYN_SENT",
    3: "SYN_RECV",
    4: "FIN_WAIT1",
    5: "FIN_WAIT2",
    6: "TIME_WAIT",
    7: "CLOSE",
    8: "CLOSE_WAIT",
    9: "LAST_ACK",
    10: "LISTEN",
    11: "CLOSING",
    128: "NONE",
}

# =====================================================================
# --- network
# =====================================================================


def net_connections(kind='inet'):
    """Return system-wide network connections .

    Cygwin has no /proc/net/tcp. Uses iphlpapi.dll via ctypes.
    """
    import ctypes
    from ctypes import byref
    from ctypes import c_ulong
    from struct import pack
    from struct import unpack_from

    from ._common import addr

    connections = []
    want_tcp = kind in ('inet', 'inet4', 'tcp', 'tcp4', 'all')
    want_udp = kind in ('inet', 'inet4', 'udp', 'udp4', 'all')

    try:
        iphlpapi = ctypes.CDLL('iphlpapi.dll')
    except OSError:
        return connections

    AF_INET = socket.AF_INET

    if want_tcp:
        # GetExtendedTcpTable with TCP_TABLE_OWNER_PID_ALL (5)
        size = c_ulong(0)
        iphlpapi.GetExtendedTcpTable(None, byref(size), 0, 2, 5, 0)
        if size.value > 0:
            buf = ctypes.create_string_buffer(size.value)
            ret = iphlpapi.GetExtendedTcpTable(buf, byref(size), 0, 2, 5, 0)
            if ret == 0:
                raw = buf.raw
                num = unpack_from('<I', raw, 0)[0]
                # MIB_TCPROW_OWNER_PID = 24 bytes each
                # Ports are DWORDs with port in network byte order
                for i in range(num):
                    off = 4 + i * 24
                    if off + 24 > len(raw):
                        break
                    state, la, lp_raw, ra, rp_raw, pid = unpack_from(
                        '<IIIIII', raw, off)
                    lp = socket.ntohs(lp_raw & 0xFFFF)
                    rp = socket.ntohs(rp_raw & 0xFFFF)
                    lip = socket.inet_ntoa(pack('<I', la))
                    rip = socket.inet_ntoa(pack('<I', ra))
                    laddr_t = addr(lip, lp)
                    raddr_t = addr(rip, rp) if (ra or rp) else ()
                    status = TCP_STATUSES.get(state, "NONE")
                    conn = conn_to_ntuple(
                        -1, AF_INET, socket.SOCK_STREAM,
                        laddr_t, raddr_t, status, TCP_STATUSES, pid)
                    connections.append(conn)

    if want_udp:
        # GetExtendedUdpTable with UDP_TABLE_OWNER_PID (1)
        size = c_ulong(0)
        iphlpapi.GetExtendedUdpTable(None, byref(size), 0, 2, 1, 0)
        if size.value > 0:
            buf = ctypes.create_string_buffer(size.value)
            ret = iphlpapi.GetExtendedUdpTable(buf, byref(size), 0, 2, 1, 0)
            if ret == 0:
                raw = buf.raw
                num = unpack_from('<I', raw, 0)[0]
                # MIB_UDPROW_OWNER_PID = 12 bytes each
                for i in range(num):
                    off = 4 + i * 12
                    if off + 12 > len(raw):
                        break
                    la, lp_raw, pid = unpack_from('<III', raw, off)
                    lp = socket.ntohs(lp_raw & 0xFFFF)
                    lip = socket.inet_ntoa(pack('<I', la))
                    laddr_t = addr(lip, lp)
                    conn = conn_to_ntuple(
                        -1, AF_INET, socket.SOCK_DGRAM,
                        laddr_t, (), "NONE", TCP_STATUSES, pid)
                    connections.append(conn)

    return connections


def net_if_addrs():
    """Return network interface addresses."""
    # Use C extension for network interface addresses
    # C extension returns list of tuples:
    # (name, family, address, netmask, broadcast, ptp)
    # Return this directly as psutil.__init__.py expects a list
    # sort
    cext_result = cext.net_if_addrs()
    if cext_result:
        # Filter out AF_UNSPEC (family=0) and empty-address entries.
        # Convert empty strings to None for broadcast/ptp fields —
        # upstream expects None, not '', for absent values.
        filtered = []
        for name, family, addr, mask, bcast, ptp in cext_result:
            if family == 0 or not addr:
                continue
            filtered.append((
                name, family, addr,
                mask or None,
                bcast or None,
                ptp or None,
            ))
        return filtered
    # If empty, fall through to fallback logic

    # Fallback: Try to get network interface info from system
    fallback_interfaces = []

    # Try to get loopback interface
    # AF_INET = 2
    fallback_interfaces.append(('lo', 2, '127.0.0.1', '255.0.0.0', None, None))

    # Try to find additional interfaces using various methods
    try:
        # Method 1: Try to parse ifconfig output
        result = subprocess.run(
            ['ifconfig'],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse ifconfig output to extract interface names and addresses
            lines = result.stdout.split('\n')
            current_iface = None
            for line in lines:
                line = line.strip()
                if line and not line.startswith(' '):
                    # New interface line
                    parts = line.split()
                    if parts:
                        current_iface = parts[0].rstrip(':')
                        # Skip lo since we already added it
                        if current_iface == 'lo':
                            current_iface = None
                elif current_iface and 'inet ' in line:
                    # Extract IP address
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'inet' and i + 1 < len(parts):
                            ip_addr = parts[i + 1]
                            # Basic validation
                            if '.' in ip_addr and ip_addr != '127.0.0.1':
                                fallback_interfaces.append((
                                    current_iface,
                                    2,
                                    ip_addr,
                                    '255.255.255.0',
                                    None,
                                    None,
                                ))
                            break
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired):
        pass  # ifconfig failed, continue with just loopback

    # Method 2: Try to get interfaces from /sys/class/net
    try:
        net_dir = '/sys/class/net'
        if os.path.exists(net_dir):
            additional_interfaces = [
                (iface, 2, '0.0.0.0', '255.255.255.0', None, None)
                for iface in os.listdir(net_dir)
                if iface != 'lo'  # Skip loopback, already added
            ]
            fallback_interfaces.extend(additional_interfaces)
    except (OSError, FileNotFoundError):
        pass

    # Remove duplicates by interface name
    seen_interfaces = set()
    unique_interfaces = []
    for iface_data in fallback_interfaces:
        iface_name = iface_data[0]
        if iface_name not in seen_interfaces:
            seen_interfaces.add(iface_name)
            unique_interfaces.append(iface_data)

    return unique_interfaces or [
        ('lo', 2, '127.0.0.1', '255.0.0.0', None, None)
    ]


def net_if_stats():
    """Return network interface stats helpers."""
    from ._common import NIC_DUPLEX_FULL
    from ._common import NIC_DUPLEX_HALF
    from ._common import NIC_DUPLEX_UNKNOWN
    from ._common import snicstats

    ret = {}
    names = set(r[0] for r in net_if_addrs())
    for name in names:
        try:
            mtu = cext.net_if_mtu(name)
            isup = bool(cext.net_if_is_running(name))
            duplex, speed = cext.net_if_duplex_speed(name)
            if duplex == 1:
                duplex = NIC_DUPLEX_HALF
            elif duplex == 2:
                duplex = NIC_DUPLEX_FULL
            else:
                duplex = NIC_DUPLEX_UNKNOWN
            if speed < 0:
                speed = 0
            if mtu < 0:
                mtu = 0
            ret[name] = snicstats(isup, duplex, speed, mtu, '')
        except OSError:
            continue
    return ret


def net_io_counters():
    """Return network I/O counters .

    Returns a dict of {name: snetio} as __init__.py expects.
    Uses ctypes to avoid WinSock header contamination in the C layer.
    Field offsets determined empirically from Cygwin's MIB_IFROW struct.
    """
    import ctypes
    from ctypes import byref
    from ctypes import c_ulong
    from struct import unpack_from

    from ._common import snetio

    try:
        iphlpapi = ctypes.CDLL('iphlpapi.dll')
    except OSError:
        return {}

    # Query required buffer size
    size = c_ulong(0)
    iphlpapi.GetIfTable(None, byref(size), 0)
    if size.value == 0:
        return {}

    buf = ctypes.create_string_buffer(size.value)
    ret = iphlpapi.GetIfTable(buf, byref(size), 0)
    if ret != 0:
        return {}

    raw = buf.raw
    num_entries = unpack_from('<I', raw, 0)[0]
    ROW_SIZE = 860  # sizeof(MIB_IFROW) on this platform

    # Field offsets within MIB_IFROW (from C offsetof)
    OFF_IN_OCTETS = 552
    OFF_IN_UCAST = 556
    OFF_IN_NUCAST = 560
    OFF_IN_DISCARDS = 564
    OFF_IN_ERRORS = 568
    OFF_OUT_OCTETS = 576
    OFF_OUT_UCAST = 580
    OFF_OUT_NUCAST = 584
    OFF_OUT_DISCARDS = 588
    OFF_OUT_ERRORS = 592
    OFF_DESCR_LEN = 600
    OFF_DESCR = 604

    result = {}
    for i in range(num_entries):
        base = 4 + i * ROW_SIZE
        if base + ROW_SIZE > len(raw):
            break

        descr_len = unpack_from('<I', raw, base + OFF_DESCR_LEN)[0]
        if descr_len > 256:
            descr_len = 256
        name = raw[base + OFF_DESCR:base + OFF_DESCR + descr_len]
        name = name.rstrip(b'\x00').decode('ascii', 'replace').strip()
        if not name:
            name = f"iface{i}"

        bytes_recv = unpack_from('<I', raw, base + OFF_IN_OCTETS)[0]
        bytes_sent = unpack_from('<I', raw, base + OFF_OUT_OCTETS)[0]
        pkts_recv = (unpack_from('<I', raw, base + OFF_IN_UCAST)[0]
                     + unpack_from('<I', raw, base + OFF_IN_NUCAST)[0])
        pkts_sent = (unpack_from('<I', raw, base + OFF_OUT_UCAST)[0]
                     + unpack_from('<I', raw, base + OFF_OUT_NUCAST)[0])
        errin = unpack_from('<I', raw, base + OFF_IN_ERRORS)[0]
        errout = unpack_from('<I', raw, base + OFF_OUT_ERRORS)[0]
        dropin = unpack_from('<I', raw, base + OFF_IN_DISCARDS)[0]
        dropout = unpack_from('<I', raw, base + OFF_OUT_DISCARDS)[0]

        result[name] = snetio(
            bytes_sent, bytes_recv, pkts_sent, pkts_recv,
            errin, errout, dropin, dropout,
        )

    return result


# =====================================================================
# --- disk
# =====================================================================


def disk_partitions(all=False):
    """Return mounted disk partitions.
        Return proper namedtuples with mountpoint attribute
    """
    try:
        # Get raw data from C extension
        # C extension returns list of tuples: (device, mountpoint, fstype,
        # opts)
        raw_partitions = cext.disk_partitions(1 if all else 0)

        # Convert raw tuples to proper namedtuples
        partitions = []
        for raw_part in raw_partitions:
            if isinstance(raw_part, (tuple, list)) and len(raw_part) == 4:
                device, mountpoint, fstype, opts = raw_part
                part = sdiskpart(device, mountpoint, fstype, opts)
                partitions.append(part)

        return partitions

    except (AttributeError, OSError):
        # Fallback: return empty list if C extension fails
        return []


def disk_usage(path):
    """Return disk usage statistics for path."""
    try:
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        # C extension returns tuple: (total, used, free, percent)
        result = cext.disk_usage(path)
        return sdiskusage(*result)
    except (AttributeError, OSError):
        # Fallback: manual calculation using os.statvfs
        statvfs = os.statvfs(path)
        total = statvfs.f_blocks * statvfs.f_frsize
        free = statvfs.f_bavail * statvfs.f_frsize
        used = total - (statvfs.f_bfree * statvfs.f_frsize)
        percent = (used / total * 100) if total > 0 else 0.0
        return sdiskusage(total, used, free, percent)


def disk_io_counters(perdisk=False):
    """Return disk I/O statistics.
    The perdisk parameter is handled by the caller, not by this function.
    """
    # Use C extension for disk I/O counters
    # C extension returns dictionary with disk names as keys
    # and tuples (read_count, write_count, read_bytes, write_bytes,
    # read_time, write_time) as values
    from collections import namedtuple

    sdiskio = namedtuple(
        'sdiskio',
        [
            'read_count',
            'write_count',
            'read_bytes',
            'write_bytes',
            'read_time',
            'write_time',
        ],
    )

    try:
        ret = cext.disk_io_counters()
        if not ret:
            # Return empty dict if no data available
            return {}

        # Convert tuples to namedtuples and return the dictionary
        return {name: sdiskio(*values) for name, values in ret.items()}
    except (AttributeError, OSError):
        # Return empty dict if C extension fails
        return {}


# =====================================================================
# --- CPU / memory
# =====================================================================


# System-wide cpu_times uses the same 10-field tuple as per_cpu_times
scputimes = scputimes_per_cpu


def cpu_times():
    """Return system-wide CPU times in seconds.

    Uses the same 10-field namedtuple as per_cpu_times() for consistency.
    /proc/stat values are in jiffies (SC_CLK_TCK, typically 1000 Hz on
    Cygwin) — divide to get seconds.
    """
    try:
        clk_tck = os.sysconf("SC_CLK_TCK")
    except (AttributeError, ValueError):
        clk_tck = 1000  # Cygwin default
    try:
        with open('/proc/stat', 'rb') as f:
            line = f.readline()
            if line.startswith(b'cpu '):
                values = [float(x) / clk_tck for x in line.split()[1:]]
                while len(values) < 10:
                    values.append(0.0)
                return scputimes(*values[:10])
    except (OSError, ValueError):
        pass
    return scputimes(*(0.0,) * 10)


def per_cpu_times():
    """Return per-CPU times.
    Simplified to use C extension directly with minimal conversion logic.
    """
    # Use C extension - it's reliable and tested
    cext_times = cext.per_cpu_times()

    # Convert to named tuples if the C extension returns raw tuples
    if cext_times and not hasattr(cext_times[0], '_fields'):
        result = []
        for cpu_time in cext_times:
            if isinstance(cpu_time, (list, tuple)):
                # Pad with zeros to match expected field count (10)
                padded = list(cpu_time) + [0.0] * (10 - len(cpu_time))
                result.append(scputimes_per_cpu(*padded[:10]))
            else:
                result.append(cpu_time)  # Already a named tuple
        return result

    return cext_times


def cpu_count_logical():
    """Return number of logical CPUs.
    C extension is reliable, removed unnecessary fallback logic.
    """
    return cext.cpu_count_logical()


def cpu_count_cores():
    """Return number of physical CPU cores.
    C extension is reliable, removed unnecessary fallback logic.
    """
    return cext.cpu_count_cores()


def cpu_stats():
    """Return CPU statistics .

    /proc/stat provides interrupts. Win32 NtQuerySystemInformation
    provides context switches and syscalls (more accurate than /proc
    for these). soft_interrupts is not available on Cygwin.
    """
    interrupts = 0
    try:
        with open('/proc/stat', 'rb') as f:
            for line in f:
                if line.startswith(b'intr '):
                    interrupts = int(line.split()[1])
                    break
    except (OSError, ValueError):
        pass

    ctx_switches = 0
    syscalls = 0
    try:
        ctx_switches, syscalls = cext.cpu_stats_win32()
    except (OSError, RuntimeError):
        # Fall back to /proc/stat for ctx_switches
        try:
            with open('/proc/stat', 'rb') as f:
                for line in f:
                    if line.startswith(b'ctxt '):
                        ctx_switches = int(line.split()[1])
                        break
        except (OSError, ValueError):
            pass

    return scpustats(ctx_switches, interrupts, 0, syscalls)


def cpu_freq():
    """Return CPU frequency as a list of (current, min, max) named tuples.
    Uses Windows CallNtPowerInformation via powrprof.dll.
    """
    from ._common import scpufreq

    curr, max_ = cext.cpu_freq()
    min_ = 0.0
    return [scpufreq(float(curr), min_, float(max_))]


def virtual_memory():
    """Return virtual memory usage statistics.
    Use C extension directly instead of manual /proc/meminfo parsing.
    """
    # Get memory information from C extension
    mem_data = cext.virtual_memory()

    # C extension returns tuple:
    # (total, available, used, free, cached, buffers, shared)
    total, available, used, free = mem_data[:4]

    # Calculate percentage
    percent = (used / total * 100) if total > 0 else 0.0

    # Return svmem namedtuple
    return svmem(total, available, percent, used, free)


def swap_memory():
    """Return swap memory usage statistics.
    Use C extension directly instead of manual /proc/meminfo parsing.
    """
    # Get swap information from C extension
    # C extension returns tuple:
    # (total, used, free, percent, sin, sout)
    return sswap(*cext.swap_memory())


# =====================================================================
# --- other system functions
# =====================================================================


def boot_time():
    """Return system boot time."""
    # TODO: Implement C extension function for boot time
    # Try to get boot time from /proc/stat
    try:
        with open('/proc/stat') as f:
            for line in f:
                if line.startswith('btime'):
                    return float(line.split()[1])
    except (OSError, ValueError):
        pass

    # Fallback: use system uptime
    try:
        with open('/proc/uptime') as f:
            uptime = float(f.read().split()[0])
            return time.time() - uptime
    except (OSError, ValueError):
        return time.time()  # Last resort fallback


def users():
    """Return currently connected users."""
    # Try multiple approaches to get user information

    # Approach 1: Try parsing 'who' command output
    users_list = _users_from_who()
    if users_list:
        return users_list

    # Approach 2: Try parsing 'w' command output
    users_list = _users_from_w()
    if users_list:
        return users_list

    # Approach 3: Try to get current user as a fallback
    users_list = _users_fallback()
    return users_list


def _users_from_who():
    """Parse 'who' command output."""
    try:
        result = subprocess.run(
            ['who'], check=False, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        users_list = []
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 3:
                username = parts[0]
                terminal = parts[1]

                # Parse datetime - 'who' typically shows: Mon Jan 1 12:34
                # For simplicity, use current time as approximation
                started = time.time()

                # Extract PID if available and host info
                pid = None
                host = None

                # Look for parentheses with PID or hostname in remaining parts
                for part in parts[3:]:
                    if part.startswith('(') and part.endswith(')'):
                        inner = part[1:-1]
                        if inner.isdigit():
                            pid = int(inner)
                        else:
                            host = inner

                # Import here to avoid circular import issues
                from ._common import suser

                user_entry = suser(username, terminal, host, started, pid)
                users_list.append(user_entry)

        return users_list

    except (
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return []


def _users_from_w():
    """Parse 'w' command output as alternative."""
    try:
        result = subprocess.run(
            ['w'], check=False, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        users_list = []
        lines = result.stdout.strip().split('\n')

        # Skip header lines (usually first 2 lines)
        for line in lines[2:]:
            if not line.strip():
                continue

            parts = line.split()
            if len(parts) >= 3:
                username = parts[0]
                terminal = parts[1]
                host = parts[2] if parts[2] != '-' else None

                # Use current time as started time approximation
                started = time.time()

                # No PID typically available from 'w' command
                pid = None

                # Import here to avoid circular import issues
                from ._common import suser

                user_entry = suser(username, terminal, host, started, pid)
                users_list.append(user_entry)

        return users_list

    except (
        subprocess.SubprocessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return []


def _users_fallback():
    """Fallback: return current user if we can determine it."""
    try:
        username = getpass.getuser()

        # Try to get terminal name
        terminal = None
        try:
            if hasattr(os, 'ttyname'):
                terminal = os.ttyname(0)
                if terminal and terminal.startswith('/dev/'):
                    terminal = terminal[5:]  # Remove /dev/ prefix
        except (OSError, AttributeError):
            # If we can't get the terminal, try some common ones
            for tty in ['console', 'tty0', 'pty0']:
                if os.path.exists(f'/dev/{tty}'):
                    terminal = tty
                    break

        # Try to get the current process PID as the session PID
        pid = os.getpid()

        # Import here to avoid circular import issues
        from ._common import suser

        user_entry = suser(username, terminal, None, time.time(), pid)
        return [user_entry]

    except (ImportError, OSError, AttributeError):
        return []


# =====================================================================
# --- processes
# =====================================================================


def sensors_battery():
    """Return battery information, or None if no battery is installed.
    Uses Windows GetSystemPowerStatus via kernel32.
    """
    from ._common import POWER_TIME_UNKNOWN
    from ._common import POWER_TIME_UNLIMITED
    from ._common import sbattery

    acline_status, flags, percent, secsleft = cext.sensors_battery()
    power_plugged = acline_status == 1
    no_battery = bool(flags & 128)
    charging = bool(flags & 8)

    if no_battery:
        return None
    if power_plugged or charging:
        secsleft = POWER_TIME_UNLIMITED
    elif secsleft == -1:
        secsleft = POWER_TIME_UNKNOWN

    return sbattery(percent, secsleft, power_plugged)


def pids():
    """Return a list of PIDs currently running on the system."""
    # Merge two sources: cygwin_internal(CW_GETPINFO) via C extension
    # skips zombie processes, but /proc readdir includes them (though
    # /proc readdir also skips some zombies — see cygwin issue).
    try:
        result = set(cext.pids())
    except (AttributeError, OSError):
        result = set()
    try:
        result.update(int(x) for x in os.listdir('/proc') if x.isdigit())
    except OSError:
        pass
    return sorted(result)


def pid_exists(pid):
    """Check if process ID exists.

    Returns False for negative PIDs to match standard psutil behavior.
    """
    # Handle negative PIDs - they should return False
    if pid < 0:
        return False

    # Handle PID 0 - has special meaning in kill() but is not a process
    if pid == 0:
        return False

    # Use the common POSIX implementation for positive PIDs
    return _psposix.pid_exists(pid)


def _win32_pid_alive(pid):
    """Check if the Windows process behind a Cygwin PID is still alive.

    Cygwin's /proc/[pid]/ can persist after the Windows process dies.
    This checks the Win32 side via PID conversion — returns False only
    if both Win32 and POSIX agree the process is gone. Includes a brief
    retry to handle the race between Cygwin fork and Windows process
    creation (a brand-new process may not have a Windows PID yet).
    """
    try:
        cext.proc_create_time_win32(pid)
        return True
    except (OSError, ProcessLookupError):
        # Win32 can't see it. Could be dead, or could be a new process
        # that hasn't registered its Windows PID yet. Check POSIX.
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        # POSIX says alive but Win32 doesn't see it — retry once after
        # a brief pause to let the Cygwin/Win32 PID mapping settle.
        time.sleep(0.05)
        try:
            cext.proc_create_time_win32(pid)
            return True
        except (OSError, ProcessLookupError):
            # Still not visible to Win32 but POSIX says alive — trust POSIX.
            return True


def _looks_like_stale_result(result):
    """Return True if a Process method result could be stale /proc data.

    Dead processes on Cygwin return "empty" values from /proc instead of
    raising errors. We check containers and None — but NOT plain integers,
    since 0 is a common valid return (nice, cpu_num, etc.).
    """
    if result is None or result == [] or result == '' or result == ():
        return True
    if isinstance(result, tuple) and all(v == 0 or v == 0.0 for v in result):
        return True
    return False


def wrap_exceptions(fun):
    """Wrapper to convert OSError exceptions.

    Includes a retry for transient /proc failures — Cygwin's /proc
    can return ENOENT for live processes under load. Without the
    retry, these get misdiagnosed as ZombieProcess.
    """

    @functools.wraps(fun)
    def wrapper(self, *args, **kwargs):
        try:
            result = fun(self, *args, **kwargs)
        except (FileNotFoundError, ProcessLookupError) as e:
            if not pid_exists(self.pid):
                raise NoSuchProcess(self.pid, self._name) from e
            # Cygwin /proc reads can transiently fail under load.
            # Retry once before concluding zombie.
            time.sleep(0.05)
            try:
                result = fun(self, *args, **kwargs)
            except (FileNotFoundError, ProcessLookupError) as e2:
                if not pid_exists(self.pid):
                    raise NoSuchProcess(self.pid, self._name) from e2
                raise ZombieProcess(
                    self.pid, self._name, self._ppid) from e2
        except PermissionError as e:
            raise AccessDenied(self.pid, self._name) from e

        return result

    return wrapper




class Process:
    """Cygwin process implementation."""

    __slots__ = ["_cache", "_name", "_ppid", "pid"]

    def __init__(self, pid):
        self.pid = pid
        self._name = None
        self._ppid = None

    def oneshot_enter(self):
        pass

    def oneshot_exit(self):
        pass

    @wrap_exceptions
    def name(self):
        """Return process name (basename of executable path)."""
        name = cext.proc_name(self.pid)
        if name and '/' in name:
            name = os.path.basename(name)
        return name

    @wrap_exceptions
    def exe(self):
        """Get process executable path."""
        return cext.proc_exe(self.pid)

    @wrap_exceptions
    def cmdline(self):
        """Get process command line."""
        return cext.proc_cmdline(self.pid)

    @wrap_exceptions
    def ppid(self):
        """Get parent process ID."""
        return cext.proc_ppid(self.pid)

    @wrap_exceptions
    def status(self):
        """Return process status as a STATUS_* string.

        Reads /proc/[pid]/stat field 3 (single letter) which is more
        accurate than the Cygwin process table — the process table
        doesn't clear PID_STOPPED after SIGCONT.
        """
        try:
            with open(f'/proc/{self.pid}/stat', 'rb') as f:
                data = f.read()
            # Field 3 is after "(comm) " — find the closing paren
            i = data.rfind(b') ')
            if i != -1:
                letter = chr(data[i + 2])
                return PROC_STATUSES_LETTER.get(letter, '?')
        except (OSError, IndexError, ValueError):
            pass
        # Fallback to C extension
        code = cext.proc_status(self.pid)
        return PROC_STATUSES.get(code, '?')

    @wrap_exceptions
    def uids(self):
        """Get process user IDs."""
        try:
            with open(f'/proc/{self.pid}/status') as f:
                for line in f:
                    if line.startswith('Uid:'):
                        fields = line.split()
                        real = int(fields[1])
                        effective = int(fields[2])
                        saved = int(fields[3])
                        return puids(real, effective, saved)
        except (OSError, ValueError, IndexError):
            return puids(0, 0, 0)

    @wrap_exceptions
    def gids(self):
        """Get process group IDs."""
        try:
            with open(f'/proc/{self.pid}/status') as f:
                for line in f:
                    if line.startswith('Gid:'):
                        fields = line.split()
                        real = int(fields[1])
                        effective = int(fields[2])
                        saved = int(fields[3])
                        return pgids(real, effective, saved)
        except (OSError, ValueError, IndexError):
            return pgids(0, 0, 0)

    @wrap_exceptions
    def create_time(self):
        """Return process creation time with 100ns resolution.

        Uses Win32 GetProcessTimes for sub-second precision, which is
        critical for PID reuse detection. Falls back to Cygwin's
        /proc-based time_t (1-second resolution) if Win32 call fails
        for a process that is still alive (e.g., system processes that
        can't be opened). If both Win32 and os.kill fail,
        the process is genuinely dead — raise NoSuchProcess even if
        /proc/[pid]/ still has stale data.
        """
        for attempt in range(3):
            try:
                return cext.proc_create_time_win32(self.pid)
            except (OSError, ProcessLookupError):
                try:
                    os.kill(self.pid, 0)
                except ProcessLookupError:
                    if attempt < 2:
                        # Both Win32 and POSIX transiently fail under
                        # load. Retry with increasing delay.
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    raise NoSuchProcess(self.pid, self._name)
                except PermissionError:
                    pass  # alive but access denied
                return cext.proc_create_time(self.pid)
        raise NoSuchProcess(self.pid, self._name)

    @wrap_exceptions
    def memory_info(self):
        """Return process memory info.

        RSS and VMS from Win32 GetProcessMemoryInfo (accurate).
        shared/text/lib/data from /proc/[pid]/status (supplemental).
        """
        raw = list(cext.proc_memory_info(self.pid))
        # raw = [rss, vms, shared, text, lib, data, dirty]
        # Win32 path returns zeros for fields 2-6; fill from /proc
        if raw[2] == 0 and raw[3] == 0:
            try:
                with open(f'/proc/{self.pid}/status', 'rb') as f:
                    for line in f:
                        if line.startswith(b'VmData:'):
                            raw[5] = int(line.split()[1]) * 1024
                        elif line.startswith(b'VmExe:'):
                            raw[3] = int(line.split()[1]) * 1024
                        elif line.startswith(b'VmLib:'):
                            raw[4] = int(line.split()[1]) * 1024
            except (OSError, ValueError):
                pass
        return pmem(*raw)

    @wrap_exceptions
    def memory_full_info(self):
        """Return extended process memory info (RSS, VMS, USS, PSS, swap)."""
        return pfullmem(*cext.proc_memory_full_info(self.pid))

    @wrap_exceptions
    def cpu_times(self):
        """Get process CPU times.
        Removed unnecessary fallback logic - C extension handles errors.
        """
        return pcputimes(*cext.proc_cpu_times(self.pid))

    @wrap_exceptions
    def terminal(self):
        """Return the controlling terminal device, or None.

        Cygwin's /proc/[pid]/stat field 7 (tty_nr) is always 0, but
        /proc/[pid]/ctty provides the controlling terminal path.
        """
        try:
            with open(f'/proc/{self.pid}/ctty') as f:
                tty = f.read().strip()
            return tty or None
        except (OSError, ValueError):
            return None

    @wrap_exceptions
    def environ(self):
        """Return process environment variables as a dict."""
        from ._common import ENCODING
        from ._common import ENCODING_ERRS
        from ._common import parse_environ_block

        with open(f'/proc/{self.pid}/environ', 'rb') as f:
            data = f.read()
        return parse_environ_block(data.decode(ENCODING, ENCODING_ERRS))

    @wrap_exceptions
    def cwd(self):
        """Get process current working directory."""
        try:
            return os.readlink(f'/proc/{self.pid}/cwd')
        except OSError:
            return ""

    @wrap_exceptions
    def nice_get(self):
        """Get process nice value."""
        return cext.getpriority(self.pid)

    @wrap_exceptions
    def nice_set(self, value):
        """Set process nice value."""
        return cext.setpriority(self.pid, value)

    @wrap_exceptions
    def cpu_num(self):
        """Return the CPU this process is currently running on.

        Only accurate for the current process — Win32
        GetCurrentProcessorNumber() reports the calling thread's CPU.
        For other PIDs, returns 0 (no cross-process API available).
        """
        if self.pid == os.getpid():
            import ctypes
            kernel32 = ctypes.CDLL('kernel32.dll')
            return kernel32.GetCurrentProcessorNumber()
        return 0

    @wrap_exceptions
    def ionice_get(self):
        """Return I/O priority as (ioclass, value) POSIX-style.

        Maps Win32 priority levels to POSIX IOPRIO_CLASS_* + value.
        """
        from ._common import pionice

        win32_prio = cext.proc_ionice_get(self.pid)
        ioclass, value = _WIN32_TO_IOCLASS.get(
            win32_prio, (IOPRIO_CLASS_NONE, 0))
        return pionice(ioclass, value)

    @wrap_exceptions
    def ionice_set(self, ioclass, value=None):
        """Set I/O priority from POSIX-style class + value.

        Maps POSIX IOPRIO_CLASS_* + value to Win32 priority levels.
        The mapping is lossy — Win32 has 4 levels vs POSIX class+value.
        """
        if ioclass == IOPRIO_CLASS_NONE:
            if value and value != 0:
                raise ValueError("ioclass accepts no value")
            win32_prio = 2  # Normal
        elif ioclass == IOPRIO_CLASS_RT:
            if value is not None and not (0 <= value <= 7):
                raise ValueError("value must be between 0 and 7")
            win32_prio = 3  # High
        elif ioclass == IOPRIO_CLASS_BE:
            if value is None:
                value = 0
            if not (0 <= value <= 7):
                raise ValueError("value must be between 0 and 7")
            # Map BE value range to Win32 levels:
            # value 0-3 → Normal (2), value 4-7 → Low (1)
            win32_prio = 1 if value >= 4 else 2
        elif ioclass == IOPRIO_CLASS_IDLE:
            if value and value != 0:
                raise ValueError("ioclass accepts no value")
            win32_prio = 0  # VeryLow
        else:
            raise ValueError(f"{ioclass!r} is not a valid ioclass")
        cext.proc_ionice_set(self.pid, win32_prio)

    @wrap_exceptions
    def cpu_affinity_get(self):
        """Return list of CPUs this process is allowed to run on."""
        return cext.proc_cpu_affinity_get(self.pid)

    @wrap_exceptions
    def cpu_affinity_set(self, cpus):
        """Set CPUs this process is allowed to run on."""
        allcpus = tuple(range(cpu_count_logical()))
        for cpu in cpus:
            if cpu not in allcpus:
                raise ValueError(
                    f"invalid CPU {cpu!r}; choose between {allcpus}")
        cext.proc_cpu_affinity_set(self.pid, cpus)

    @wrap_exceptions
    def rlimit(self, resource_, limits=None):
        """Get or set process resource limits.

        Cygwin only supports rlimit for the current process — POSIX
        getrlimit/setrlimit operate on the calling process only.
        """
        if self.pid != os.getpid():
            if not _win32_pid_alive(self.pid):
                raise NoSuchProcess(self.pid, self._name)
            raise AccessDenied(self.pid, self._name)
        if limits is None:
            return _resource.getrlimit(resource_)
        else:
            _resource.setrlimit(resource_, limits)

    @wrap_exceptions
    def open_files(self):
        """Return list of open regular files.

        Filters out non-regular files (/dev/null, /proc/*, etc.) using
        isfile_strict(), same approach as macOS implementation.
        """
        from ._common import isfile_strict

        files_data = cext.proc_open_files(self.pid)
        return [pfile(path, fd) for path, fd in files_data
                if isfile_strict(path)]

    @wrap_exceptions
    def net_connections(self, kind='inet'):
        """Return network connections for process.
        """
        # Get raw connection tuples from C extension
        # Format: (fd, family, type, laddr, raddr, status, pid) -
        # for process connections
        try:
            raw_connections = cext.proc_net_connections(self.pid, kind)
        except AttributeError:
            return []

        # Convert raw tuples to proper namedtuples
        connections = []
        for raw_conn in raw_connections:
            try:
                # Handle both formats - with and without PID
                if not isinstance(raw_conn, (tuple, list)):
                    continue

                if len(raw_conn) == 7:
                    # System-wide format with PID
                    fd, family, type_, laddr, raddr, status, pid = raw_conn
                elif len(raw_conn) == 6:
                    # Process-specific format without PID
                    fd, family, type_, laddr, raddr, status = raw_conn
                    pid = None
                else:
                    continue

                # Convert family and type to proper enums
                try:
                    family = sockfam_to_enum(family)
                    type_ = socktype_to_enum(type_)
                except (ValueError, KeyError):
                    # Skip connections with invalid family/type
                    continue

                # Convert addresses to proper format
                if family in {
                    socket.AF_INET,
                    getattr(socket, 'AF_INET6', None),
                }:
                    if (
                        laddr
                        and isinstance(laddr, (tuple, list))
                        and len(laddr) == 2
                    ):
                        from ._common import addr

                        laddr = addr(*laddr)
                    else:
                        laddr = None

                    if (
                        raddr
                        and isinstance(raddr, (tuple, list))
                        and len(raddr) == 2
                    ):
                        from ._common import addr

                        raddr = addr(*raddr)
                    else:
                        raddr = None

                # Convert status to string
                if isinstance(status, int):
                    status = TCP_STATUSES.get(status, "NONE")

                # Create proper namedtuple using conn_to_ntuple
                conn = conn_to_ntuple(
                    fd, family, type_, laddr, raddr, status, TCP_STATUSES, pid
                )
                connections.append(conn)

            except (ValueError, TypeError, AttributeError):
                # Skip malformed connections but continue processing
                continue

        return connections

    @wrap_exceptions
    def num_threads(self):
        """Return number of threads ."""
        return len(cext.proc_threads(self.pid))

    @wrap_exceptions
    def threads(self):
        """Return threads as list of (id, user_time, system_time).
        Uses Windows CreateToolhelp32Snapshot via kernel32.
        """
        rawlist = cext.proc_threads(self.pid)
        retlist = []
        for thread_id, utime, stime in rawlist:
            retlist.append(pthread(thread_id, utime, stime))
        return retlist

    @wrap_exceptions
    def num_ctx_switches(self):
        """Get number of context switches."""
        return pctxsw(*cext.proc_num_ctx_switches(self.pid))

    @wrap_exceptions
    def num_fds(self):
        """Get number of file descriptors."""
        return cext.proc_num_fds(self.pid)

    @wrap_exceptions
    def io_counters(self):
        """Return I/O counters ."""
        # Win32 returns (read_count, write_count, read_bytes, write_bytes,
        #                other_count, other_bytes)
        try:
            raw = cext.proc_io_counters_win32(self.pid)
            return pio(raw[0], raw[1], raw[2], raw[3])
        except (OSError, ProcessLookupError):
            # Fallback to old C extension (may return zeros)
            io_data = cext.proc_io_counters(self.pid)
            return pio(io_data[0], io_data[1], io_data[2], io_data[3])

    @wrap_exceptions
    def memory_maps(self):
        """Get memory maps.

        Returns raw memory mapping data from the C extension.
        The main Process class handles grouping if needed.
        Simplified to match other platform implementations by returning
        raw data and letting the main Process class handle grouping.
        """
        # C extension returns list of tuples with memory mapping information
        # Each tuple: (addr, perms, path, rss, size, pss, shared_clean,
        #              shared_dirty, private_clean, private_dirty,
        #              referenced, anonymous, swap)
        return cext.proc_memory_maps(self.pid)

    @wrap_exceptions
    def wait(self, timeout=None):
        """Wait for process to terminate."""
        return _psposix.wait_pid(self.pid, timeout, self._name)
