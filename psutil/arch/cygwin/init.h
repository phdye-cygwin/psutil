/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform specific header for psutil C extension
 *
 * UPDATED: Issue #052 - Added Windows API memory alignment functions
 */

#ifndef PSUTIL_CYGWIN_INIT_H
#define PSUTIL_CYGWIN_INIT_H

#include <Python.h>
#include <sys/types.h>
#include <time.h>

// Cygwin-specific function declarations
// These are the Phase 1 functions that need to be implemented

// Phase 1.2: Basic utility functions
PyObject *psutil_getpagesize_pywrapper(PyObject *self, PyObject *args);
PyObject *psutil_check_pid_range_cygwin(PyObject *self, PyObject *args);

// Phase 1.3: Network connection functions (CRITICAL)
PyObject *psutil_net_connections(PyObject *self, PyObject *args);
PyObject *psutil_proc_net_connections(PyObject *self, PyObject *args);

// Phase 1.4: Priority functions
PyObject *psutil_posix_getpriority(PyObject *self, PyObject *args);
PyObject *psutil_posix_setpriority(PyObject *self, PyObject *args);

// Cygwin platform-specific utility functions
int psutil_pid_exists(pid_t pid);
void psutil_raise_for_pid(pid_t pid, char *syscall);
long psutil_getpagesize(void);

// Additional basic utility functions (Phase 1 extensions)
PyObject *psutil_getpid(PyObject *self, PyObject *args);
PyObject *psutil_getppid(PyObject *self, PyObject *args);

// =============================================================================
// --- Memory Functions with Windows API Alignment (Issue #052)
// =============================================================================

// Enhanced memory functions that align with psx.cc calculations
PyObject *psutil_set_memory_debug(PyObject *self, PyObject *args);
PyObject *psutil_test_memory_alignment(PyObject *self, PyObject *args);

// Standard memory functions (now with Windows API alignment)
PyObject *psutil_proc_memory_info(PyObject *self, PyObject *args);
PyObject *psutil_proc_memory_full_info(PyObject *self, PyObject *args);
PyObject *psutil_proc_memory_maps(PyObject *self, PyObject *args);

// System memory functions
PyObject *psutil_virtual_memory(PyObject *self, PyObject *args);
PyObject *psutil_swap_memory(PyObject *self, PyObject *args);

// =============================================================================
// --- Centralized Caching System (Phase C1)
// =============================================================================

// Cache entry structure for generic string data
typedef struct {
    pid_t pid;
    char data[256];
    time_t cache_time;
    int is_valid;
} psutil_str_cache_t;

// Cache entry structure for numeric data
typedef struct {
    pid_t pid;
    long data;
    time_t cache_time;
    int is_valid;
} psutil_num_cache_t;

// Centralized cache structures
extern psutil_str_cache_t psutil_proc_name_cache;
extern psutil_num_cache_t psutil_proc_ppid_cache;
extern psutil_str_cache_t psutil_proc_status_cache;

// Cache management functions
void psutil_cache_init(void);
void psutil_cache_cleanup(void);
int psutil_str_cache_get(psutil_str_cache_t *cache, pid_t pid, char *result, size_t result_size, int max_age_seconds);
void psutil_str_cache_set(psutil_str_cache_t *cache, pid_t pid, const char *data);
int psutil_num_cache_get(psutil_num_cache_t *cache, pid_t pid, long *result, int max_age_seconds);
void psutil_num_cache_set(psutil_num_cache_t *cache, pid_t pid, long data);
void psutil_cache_invalidate_pid(pid_t pid);
void psutil_cache_invalidate_all(void);

// Cache configuration
#define PSUTIL_CACHE_DEFAULT_TTL 1  // 1 second default TTL

// Network parameter validation functions
int psutil_validate_connection_kind(const char *kind);

// Connection status constants - matching psutil's _common.py
#define PSUTIL_CONN_ESTABLISHED   1
#define PSUTIL_CONN_SYN_SENT      2
#define PSUTIL_CONN_SYN_RECV      3
#define PSUTIL_CONN_FIN_WAIT1     4
#define PSUTIL_CONN_FIN_WAIT2     5
#define PSUTIL_CONN_TIME_WAIT     6
#define PSUTIL_CONN_CLOSE         7
#define PSUTIL_CONN_CLOSE_WAIT    8
#define PSUTIL_CONN_LAST_ACK      9
#define PSUTIL_CONN_LISTEN        10
#define PSUTIL_CONN_CLOSING       11
// PSUTIL_CONN_NONE is defined in arch/all/init.c as a global variable

#endif  // PSUTIL_CYGWIN_INIT_H
