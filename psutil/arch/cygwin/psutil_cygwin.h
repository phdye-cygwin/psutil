/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform C extension - Common header file
 */

#ifndef PSUTIL_CYGWIN_H
#define PSUTIL_CYGWIN_H

#include <Python.h>

// =============================================================================
// --- Basic Utility and Wrapper Functions
// =============================================================================

// Common utility functions (implemented in arch/all/init.c)
// PyObject *psutil_check_pid_range(PyObject *self, PyObject *args); - in arch/all/init.h
// PyObject *psutil_set_debug(PyObject *self, PyObject *args); - in arch/all/init.h
int psutil_setup(void);

// Wrapper functions for routing (implemented in main file)
PyObject *psutil_getpagesize_wrapper(PyObject *self, PyObject *args);
PyObject *psutil_net_connections_wrapper(PyObject *self, PyObject *args);
PyObject *psutil_proc_net_connections_wrapper(PyObject *self, PyObject *args);
PyObject *psutil_getpriority_wrapper(PyObject *self, PyObject *args);
PyObject *psutil_setpriority_wrapper(PyObject *self, PyObject *args);

// =============================================================================
// --- Basic System Functions (arch/cygwin/init.c)
// =============================================================================

PyObject *psutil_getpid(PyObject *self, PyObject *args);
PyObject *psutil_getppid(PyObject *self, PyObject *args);
PyObject *psutil_getpagesize_posix(PyObject *self, PyObject *args);

// =============================================================================
// --- System Information Functions (arch/cygwin/system.c)
// =============================================================================

PyObject *psutil_boot_time(PyObject *self, PyObject *args);
PyObject *psutil_users(PyObject *self, PyObject *args);

// =============================================================================
// --- Process Functions (arch/cygwin/proc.c)
// =============================================================================

// Process enumeration
PyObject *psutil_pids(PyObject *self, PyObject *args);
PyObject *psutil_pid_exists_py(PyObject *self, PyObject *args);

// Basic process information
PyObject *psutil_proc_name(PyObject *self, PyObject *args);
PyObject *psutil_proc_cmdline(PyObject *self, PyObject *args);
PyObject *psutil_proc_exe(PyObject *self, PyObject *args);
PyObject *psutil_proc_ppid(PyObject *self, PyObject *args);
PyObject *psutil_proc_status(PyObject *self, PyObject *args);
PyObject *psutil_proc_create_time(PyObject *self, PyObject *args);

// Process resources
PyObject *psutil_proc_num_threads(PyObject *self, PyObject *args);
PyObject *psutil_proc_open_files(PyObject *self, PyObject *args);

// Process priority
PyObject *psutil_getpriority_posix(PyObject *self, PyObject *args);
PyObject *psutil_setpriority_posix(PyObject *self, PyObject *args);

// =============================================================================
// --- Memory Functions (arch/cygwin/mem.c)
// =============================================================================

// System memory
PyObject *psutil_virtual_memory(PyObject *self, PyObject *args);
PyObject *psutil_swap_memory(PyObject *self, PyObject *args);

// Process memory
PyObject *psutil_proc_memory_info(PyObject *self, PyObject *args);
PyObject *psutil_proc_memory_maps(PyObject *self, PyObject *args);
PyObject *psutil_proc_memory_full_info(PyObject *self, PyObject *args);

// =============================================================================
// --- CPU Functions (arch/cygwin/cpu.c)
// =============================================================================

// System CPU information
PyObject *psutil_cpu_count_logical(PyObject *self, PyObject *args);
PyObject *psutil_cpu_count_cores(PyObject *self, PyObject *args);
PyObject *psutil_per_cpu_times(PyObject *self, PyObject *args);
PyObject *psutil_cpu_times(PyObject *self, PyObject *args);
PyObject *psutil_cpu_stats(PyObject *self, PyObject *args);

// Process CPU information
PyObject *psutil_proc_cpu_times(PyObject *self, PyObject *args);

// =============================================================================
// --- I/O Functions (arch/cygwin/io.c)
// =============================================================================

PyObject *psutil_proc_io_counters(PyObject *self, PyObject *args);
PyObject *psutil_proc_num_ctx_switches(PyObject *self, PyObject *args);
PyObject *psutil_proc_num_fds(PyObject *self, PyObject *args);

// =============================================================================
// --- Network Functions (arch/cygwin/net.c)
// =============================================================================

// Network interface functions (Pure POSIX)
PyObject *psutil_net_if_addrs(PyObject* self, PyObject* args);
PyObject *psutil_net_if_mtu(PyObject *self, PyObject *args);
PyObject *psutil_net_if_flags(PyObject *self, PyObject *args);
PyObject *psutil_net_if_is_running(PyObject *self, PyObject *args);
PyObject *psutil_net_if_duplex_speed(PyObject *self, PyObject *args);

// Network connections (POSIX implementations)
PyObject *psutil_net_connections_posix(PyObject *self, PyObject *args);
PyObject *psutil_proc_net_connections_posix(PyObject *self, PyObject *args);

// Network connection wrapper functions - route to POSIX implementations
PyObject *psutil_net_connections(PyObject *self, PyObject *args);
PyObject *psutil_proc_net_connections(PyObject *self, PyObject *args);

// =============================================================================
// --- Disk Functions (arch/cygwin/disk.c)
// =============================================================================

PyObject *psutil_disk_partitions(PyObject *self, PyObject *args);
PyObject *psutil_disk_usage(PyObject *self, PyObject *args);
PyObject *psutil_disk_io_counters(PyObject *self, PyObject *args);

// =============================================================================
// --- Windows Implementation Functions (arch/cygwin/win32.c)
// =============================================================================

// Network connections (Windows API implementations)
PyObject *psutil_net_connections_win32(PyObject *self, PyObject *args);
PyObject *psutil_proc_net_connections_win32(PyObject *self, PyObject *args);

// System functions (Windows API implementations)
PyObject *psutil_getpagesize_win32(PyObject *self, PyObject *args);

// Windows-specific initialization/cleanup
int psutil_win32_init(void);
void psutil_win32_cleanup(void);

// =============================================================================
// --- Win32 API Functions (arch/cygwin/win32_apis.c)
// =============================================================================

PyObject *psutil_cpu_freq_win32(PyObject *self, PyObject *args);
PyObject *psutil_sensors_battery_win32(PyObject *self, PyObject *args);
PyObject *psutil_proc_threads_win32(PyObject *self, PyObject *args);
PyObject *psutil_proc_cpu_affinity_get_win32(PyObject *self, PyObject *args);
PyObject *psutil_proc_cpu_affinity_set_win32(PyObject *self, PyObject *args);
PyObject *psutil_proc_ionice_get_win32(PyObject *self, PyObject *args);

#endif  // PSUTIL_CYGWIN_H
