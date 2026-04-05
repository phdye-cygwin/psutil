/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform C extension - Main module
 * This file contains only Python bindings and routing - no platform headers
 *
 * UPDATED: Converted to use consistent POSIX socket APIs throughout
 * Removed WinSock dependencies to work properly with Cygwin's POSIX socket layer
 *
 * UPDATED: Issue #052 - Added Windows API memory alignment functions
 */

#include <Python.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/sysinfo.h>
#include <dirent.h>

#include "arch/cygwin/psutil_cygwin.h"
#include "arch/cygwin/init.h"
#include "arch/all/init.h"    // Include global psutil declarations

// == ===========================================================================
// --- Function Routing (dispatch to appropriate implementations)
// == ===========================================================================

// Route getpagesize to the best implementation (try POSIX first, fallback to Windows)
PyObject *
psutil_getpagesize_wrapper(PyObject *self, PyObject *args)
{
    PyObject *result = psutil_getpagesize_posix(self, args);

    // If POSIX implementation fails, try Windows implementation
    if (result && PyLong_AsLong(result) > 0) {
        return result;
    }

    Py_XDECREF(result);
    return psutil_getpagesize_win32(self, args);
}

// Route network connections to POSIX implementation (consistent with Cygwin environment)
PyObject *
psutil_net_connections_wrapper(PyObject *self, PyObject *args)
{
    return psutil_net_connections_posix(self, args);
}

// Route process network connections to POSIX implementation
PyObject *
psutil_proc_net_connections_wrapper(PyObject *self, PyObject *args)
{
    return psutil_proc_net_connections_posix(self, args);
}

// Route priority functions to POSIX implementations
PyObject *
psutil_getpriority_wrapper(PyObject *self, PyObject *args)
{
    return psutil_getpriority_posix(self, args);
}

PyObject *
psutil_setpriority_wrapper(PyObject *self, PyObject *args)
{
    return psutil_setpriority_posix(self, args);
}

// == ===========================================================================
// --- Module Infrastructure
// == ===========================================================================

// Forward declaration of cleanup function
static void module_free(void *m);

// Module method definitions - organized by functional category
static PyMethodDef mod_methods[] = {
    // Basic utility functions (arch/cygwin/init.c)
    {"getpagesize", psutil_getpagesize_wrapper, METH_VARARGS,
     "Return system page size"},
    {"check_pid_range", psutil_check_pid_range, METH_VARARGS,
     "Check if PID is in valid range and exists"},
    {"set_debug", psutil_set_debug, METH_VARARGS,
     "Enable or disable debug mode"},
    {"getpid", psutil_getpid, METH_VARARGS,
     "Get current process ID"},
    {"getppid", psutil_getppid, METH_VARARGS,
     "Get parent process ID of current process"},

    // System information functions (arch/cygwin/system.c)
    {"boot_time", psutil_boot_time, METH_VARARGS,
     "Get system boot time"},
    {"users", psutil_users, METH_VARARGS,
     "Get system users currently logged in"},
    {"getpriority", psutil_getpriority_wrapper, METH_VARARGS,
     "Get process priority"},
    {"setpriority", psutil_setpriority_wrapper, METH_VARARGS,
     "Set process priority"},

    // Process list and basic process functions (arch/cygwin/proc.c)
    {"pids", psutil_pids, METH_VARARGS,
     "Get list of all process IDs"},
    {"pid_exists", psutil_pid_exists_py, METH_VARARGS,
     "Check if a process exists"},
    {"proc_name", psutil_proc_name, METH_VARARGS,
     "Get process name"},
    {"proc_cmdline", psutil_proc_cmdline, METH_VARARGS,
     "Get process command line"},
    {"proc_exe", psutil_proc_exe, METH_VARARGS,
     "Get process executable path"},
    {"proc_ppid", psutil_proc_ppid, METH_VARARGS,
     "Get parent process ID"},
    {"proc_status", psutil_proc_status, METH_VARARGS,
     "Get process status"},
    {"proc_create_time", psutil_proc_create_time, METH_VARARGS,
     "Get process creation time"},
    {"proc_num_threads", psutil_proc_num_threads, METH_VARARGS,
     "Get number of threads for a process"},
    {"proc_open_files", psutil_proc_open_files, METH_VARARGS,
     "Get list of open files for a process"},

    // Memory functions (arch/cygwin/mem.c) - WITH WINDOWS API ALIGNMENT
    {"virtual_memory", psutil_virtual_memory, METH_VARARGS,
     "Get virtual memory information"},
    {"swap_memory", psutil_swap_memory, METH_VARARGS,
     "Get swap memory information"},
    {"proc_memory_info", psutil_proc_memory_info, METH_VARARGS,
     "Get process memory information - Windows API aligned (Issue #052)"},
    {"proc_memory_maps", psutil_proc_memory_maps, METH_VARARGS,
     "Get process memory mapping information"},
    {"proc_memory_full_info", psutil_proc_memory_full_info, METH_VARARGS,
     "Get extended process memory information - Windows API aligned (Issue #052)"},

    // Memory alignment and testing functions (Issue #052)
    {"set_memory_debug", psutil_set_memory_debug, METH_VARARGS,
     "Enable/disable memory alignment debug output"},
    {"test_memory_alignment", psutil_test_memory_alignment, METH_VARARGS,
     "Test memory alignment with psx.cc - returns (RSS, VSZ) in bytes"},

    // CPU functions (arch/cygwin/cpu.c)
    {"cpu_count_logical", psutil_cpu_count_logical, METH_VARARGS,
     "Get logical CPU count"},
    {"cpu_count_cores", psutil_cpu_count_cores, METH_VARARGS,
     "Get physical CPU core count"},
    {"per_cpu_times", psutil_per_cpu_times, METH_VARARGS,
     "Get per-CPU time information"},
    {"cpu_times", psutil_cpu_times, METH_VARARGS,
     "Get system-wide CPU times"},
    {"cpu_stats", psutil_cpu_stats, METH_VARARGS,
     "Get system CPU statistics"},
    {"proc_cpu_times", psutil_proc_cpu_times, METH_VARARGS,
     "Get process CPU times"},

    // I/O functions (arch/cygwin/io.c)
    {"proc_io_counters", psutil_proc_io_counters, METH_VARARGS,
     "Get process I/O counters"},
    {"proc_num_ctx_switches", psutil_proc_num_ctx_switches, METH_VARARGS,
     "Get process context switch count"},
    {"proc_num_fds", psutil_proc_num_fds, METH_VARARGS,
     "Get number of open file descriptors"},

    // Network interface functions (arch/cygwin/net.c) - Pure POSIX
    {"net_if_addrs", psutil_net_if_addrs, METH_VARARGS,
     "Get network interface addresses"},
    {"net_if_mtu", psutil_net_if_mtu, METH_VARARGS,
     "Get network interface MTU"},
    {"net_if_flags", psutil_net_if_flags, METH_VARARGS,
     "Get network interface flags"},
    {"net_if_is_running", psutil_net_if_is_running, METH_VARARGS,
     "Check if network interface is running"},
    {"net_if_duplex_speed", psutil_net_if_duplex_speed, METH_VARARGS,
     "Get network interface duplex and speed"},

    // Network connection functions (using POSIX implementations)
    {"net_connections", psutil_net_connections_wrapper, METH_VARARGS,
     "Get system-wide network connections"},
    {"proc_net_connections", psutil_proc_net_connections_wrapper, METH_VARARGS,
     "Get network connections for a specific process"},

    // Disk functions (arch/cygwin/disk.c)
    {"disk_partitions", psutil_disk_partitions, METH_VARARGS,
     "Get disk partition information"},
    {"disk_usage", psutil_disk_usage, METH_VARARGS,
     "Get disk usage statistics"},
    {"disk_io_counters", psutil_disk_io_counters, METH_VARARGS,
     "Get disk I/O statistics"},

    // Win32 API functions (arch/cygwin/win32_apis.c)
    {"cpu_freq", psutil_cpu_freq_win32, METH_VARARGS,
     "Return CPU frequency as (current_mhz, max_mhz)"},
    {"sensors_battery", psutil_sensors_battery_win32, METH_VARARGS,
     "Return battery info as (acline_status, flags, percent, secsleft)"},
    {"proc_threads", psutil_proc_threads_win32, METH_VARARGS,
     "Return list of (thread_id, user_time, system_time) for a process"},

    {NULL, NULL, 0, NULL}
};

// Module definition structure
static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "_psutil_cygwin",
    "Cygwin C extension for psutil - POSIX-consistent with Windows API memory alignment (Issue #052)",
    -1,
    mod_methods,
    NULL,
    NULL,
    NULL,
    module_free  // Add cleanup function
};

// == ===========================================================================
// --- Module Cleanup
// == ===========================================================================

static void
module_free(void *m)
{
    // Call cleanup functions - no WinSock cleanup needed for POSIX approach
    // Only call win32 cleanup if it's safe to do so
    // This maintains compatibility while avoiding WinSock dependencies
}

// == ===========================================================================
// --- Module Initialization
// == ===========================================================================

PyObject *
PyInit__psutil_cygwin(void)
{
    PyObject *mod = NULL;

    // Create the module
    mod = PyModule_Create(&moduledef);
    if (mod == NULL) {
        return NULL;
    }

#ifdef Py_GIL_DISABLED
    if (PyUnstable_Module_SetGIL(mod, Py_MOD_GIL_NOT_USED)) {
        return NULL;
    }
#endif

    // No WinSock initialization - let Cygwin handle POSIX sockets naturally
    // This allows all socket operations to work through Cygwin's POSIX layer

    // Set up module constants for network connection states
    if (PyModule_AddIntConstant(mod, "CONN_ESTABLISHED", 1)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_SYN_SENT", 2)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_SYN_RECV", 3)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_FIN_WAIT1", 4)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_FIN_WAIT2", 5)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_TIME_WAIT", 6)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_CLOSE", 7)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_CLOSE_WAIT", 8)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_LAST_ACK", 9)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_LISTEN", 10)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_CLOSING", 11)) return NULL;
    if (PyModule_AddIntConstant(mod, "CONN_NONE", 128)) return NULL;

    // Set up version information
    if (PyModule_AddIntConstant(mod, "version", PSUTIL_VERSION)) return NULL;

    // Initialize global psutil state
    if (psutil_setup() != 0) {
        return NULL;
    }

    return mod;
}
