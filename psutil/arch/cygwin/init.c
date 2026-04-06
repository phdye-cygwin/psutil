/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform specific initialization and common functions.
 * This file provides Cygwin-specific implementations and utilities
 * without duplicating symbols already defined in arch/all/init.c
 */

#include <Python.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/cygwin.h>
#include <time.h>
#include <unistd.h>
#include <windows.h>
#include "psutil_cygwin.h"
#include "../all/init.h"

// Debug privilege management from ps.cc
static int
enable_debug_privilege(void)
{
    HANDLE tok;
    if (!OpenProcessToken(GetCurrentProcess(),
                         TOKEN_QUERY | TOKEN_ADJUST_PRIVILEGES,
                         &tok)) {
        return 0;  // Failed to open token
    }

    TOKEN_PRIVILEGES priv;
    priv.PrivilegeCount = 1;

    if (!LookupPrivilegeValue(NULL, SE_DEBUG_NAME, &priv.Privileges[0].Luid)) {
        CloseHandle(tok);
        return 0;  // Failed to lookup privilege
    }

    priv.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED;
    BOOL result = AdjustTokenPrivileges(tok, FALSE, &priv, 0, NULL, NULL);

    CloseHandle(tok);
    return result ? 1 : 0;
}

/*
 * Enhanced Cygwin-specific initialization routine.
 * This is called by the main psutil_setup() function in arch/all/init.c
 * via platform-specific hooks if needed.
 */
int
psutil_cygwin_init(void)
{
    // Enable debug privilege for complete process access like ps.cc
    if (!enable_debug_privilege()) {
        // Log warning but don't fail - we can still get most processes
        fprintf(stderr, "psutil: Warning - could not enable debug privilege, "
                       "some system processes may not be accessible\n");
    }

    return 0;  // Success
}

/*
 * Cygwin-specific cleanup routine.
 * Called during module cleanup if needed.
 */
void
psutil_cygwin_cleanup(void)
{
    // Any Cygwin-specific cleanup can go here
    // For now, we don't need any special cleanup
}

/*
 * Cygwin-specific PID range validation.
 * This provides additional validation on top of the generic check
 * in arch/all/init.c if needed.
 */
int
psutil_cygwin_check_pid_range(pid_t pid)
{
    // On Cygwin/Windows, PIDs are typically in a smaller range
    // than on pure Unix systems, but we'll be permissive for now
    if (pid < 0 || pid > 2147483647) {  // Max signed 32-bit int
        return 0;  // Invalid
    }

    return 1;  // Valid
}

/*
 * Check if a process with the given PID exists.
 * Return values:
 * 1: exists
 * 0: does not exist
 * -1: error (Python exception is set)
 *
 * This is the Cygwin implementation of psutil_pid_exists.
 * It uses both Unix-style signal checking and /proc filesystem.
 * PID 0 should exist (system idle process)
 */
int
psutil_pid_exists(pid_t pid)
{
    int ret;
    char proc_path[256];
    struct stat st;

    // No negative PID exists
    if (pid < 0)
        return 0;

    // PID 0 is special - on POSIX systems it has special meaning in kill()
    // and typically doesn't exist as a regular process that can be monitored
    if (pid == 0)
        return 0;

    // Method 1: Try to check via /proc filesystem (most reliable on Cygwin)
    snprintf(proc_path, sizeof (proc_path), "/proc/%d", (int)pid);
    if (stat(proc_path, &st) == 0) {
        // /proc/PID exists, so the process exists
        return 1;
    }

    // Method 2: Fall back to kill(pid, 0) - traditional Unix method
    ret = kill(pid, 0);
    if (ret == 0) {
        return 1;  // Process exists
    } else {
        if (errno == ESRCH) {
            // ESRCH == No such process
            return 0;
        } else if (errno == EPERM) {
            // EPERM clearly indicates there's a process to deny access to
            return 1;
        } else {
            // Unexpected error
            PyErr_SetFromErrno(PyExc_OSError);
            return -1;
        }
    }
}

/*
 * Utility used for those syscalls which do not return a meaningful
 * error that we can translate into an exception which makes sense.
 * This is the Cygwin implementation of psutil_raise_for_pid.
 */
void
psutil_raise_for_pid(pid_t pid, char *syscall)
{
    if (errno != 0)
        psutil_PyErr_SetFromOSErrnoWithSyscall(syscall);
    else if (psutil_pid_exists(pid) == 0)
        NoSuchProcess(syscall);
    else
        PyErr_Format(PyExc_RuntimeError, "%s syscall failed", syscall);
}

/*
 * Get system page size.
 * This is the Cygwin implementation of psutil_getpagesize.
 * Enhanced version integrating POSIX implementation from phase1.
 */
long
psutil_getpagesize(void)
{
    long page_size;

    // Try sysconf first (POSIX standard)
    page_size = sysconf(_SC_PAGESIZE);
    if (page_size > 0) {
        return page_size;
    }

    // Fallback to getpagesize() if available
#ifdef _SC_PAGESIZE
    page_size = getpagesize();
    if (page_size > 0) {
        return page_size;
    }
#endif

    // Final fallback - typical page size
    return 4096;
}

/*
 * Cygwin-specific error handling utility.
 * Provides enhanced error messages for Cygwin environment.
 */
PyObject *
psutil_cygwin_error_handler(const char *syscall, int use_errno)
{
    // For now, delegate to the global error handler
    // We could add Cygwin-specific error message improvements here
    if (use_errno) {
        return psutil_PyErr_SetFromOSErrnoWithSyscall(syscall);
    }

    // Generic error without errno
    PyErr_SetString(PyExc_OSError, syscall);
    return NULL;
}

// == ===========================================================================
// --- Additional Basic Utility Functions (Extensions)
// == ===========================================================================

/*
 * Get current process ID
 * Python wrapper for getpid() system call
 */
PyObject *
psutil_getpid(PyObject *self, PyObject *args)
{
    return PyLong_FromLong((long)getpid());
}

/*
 * Get parent process ID of current process
 * Python wrapper for getppid() system call
 */
PyObject *
psutil_getppid(PyObject *self, PyObject *args)
{
    return PyLong_FromLong((long)getppid());
}

/*
 * Get system page size - POSIX implementation
 * Python wrapper that returns the system page size
 */
PyObject *
psutil_getpagesize_posix(PyObject *self, PyObject *args)
{
    long page_size;

    // Try sysconf first (POSIX standard)
    page_size = sysconf(_SC_PAGESIZE);
    if (page_size > 0) {
        return PyLong_FromLong(page_size);
    }

    // Fallback to getpagesize() if available
#ifdef _SC_PAGESIZE
    page_size = getpagesize();
    if (page_size > 0) {
        return PyLong_FromLong(page_size);
    }
#endif

    // Final fallback - typical page size
    return PyLong_FromLong(4096);
}

// == ===========================================================================
// --- Centralized Caching System Implementation
// == ===========================================================================

// Global cache instances
psutil_str_cache_t psutil_proc_name_cache = {0, "", 0, 0};
psutil_num_cache_t psutil_proc_ppid_cache = {0, 0, 0, 0};
psutil_str_cache_t psutil_proc_status_cache = {0, "", 0, 0};

/*
 * Initialize the caching system
 */
void
psutil_cache_init(void)
{
    // Clear all cache entries
    psutil_cache_invalidate_all();
}

/*
 * Cleanup the caching system
 */
void
psutil_cache_cleanup(void)
{
    // Clear all cache entries
    psutil_cache_invalidate_all();
}

/*
 * Get a string value from cache if valid
 * Returns 1 if cache hit, 0 if cache miss
 */
int
psutil_str_cache_get(psutil_str_cache_t *cache, pid_t pid, char *result,
                     size_t result_size, int max_age_seconds) {
    time_t current_time;

    if (cache == NULL || result == NULL) {
        return 0;
    }

    current_time = time(NULL);

    // Check if cache entry is valid
    if (cache->is_valid && cache->pid == pid && cache->data[0] != '\0' && (current_time - cache->cache_time) < max_age_seconds) {

        // Copy cached data to result
        strncpy(result, cache->data, result_size - 1);
        result[result_size - 1] = '\0';
        return 1;  // Cache hit
    }

    return 0;  // Cache miss
}

/*
 * Set a string value in cache
 */
void
psutil_str_cache_set(psutil_str_cache_t *cache, pid_t pid, const char *data)
{
    if (cache == NULL || data == NULL) {
        return;
    }

    cache->pid = pid;
    strncpy(cache->data, data, sizeof (cache->data) - 1);
    cache->data[sizeof (cache->data) - 1] = '\0';
    cache->cache_time = time(NULL);
    cache->is_valid = 1;
}

/*
 * Get a numeric value from cache if valid
 * Returns 1 if cache hit, 0 if cache miss
 */
int
psutil_num_cache_get(psutil_num_cache_t *cache, pid_t pid, long *result,
                     int max_age_seconds) {
    time_t current_time;

    if (cache == NULL || result == NULL) {
        return 0;
    }

    current_time = time(NULL);

    // Check if cache entry is valid
    if (cache->is_valid && cache->pid == pid && (current_time - cache->cache_time) < max_age_seconds) {

        *result = cache->data;
        return 1;  // Cache hit
    }

    return 0;  // Cache miss
}

/*
 * Set a numeric value in cache
 */
void
psutil_num_cache_set(psutil_num_cache_t *cache, pid_t pid, long data)
{
    if (cache == NULL) {
        return;
    }

    cache->pid = pid;
    cache->data = data;
    cache->cache_time = time(NULL);
    cache->is_valid = 1;
}

/*
 * Invalidate all cache entries for a specific PID
 */
void
psutil_cache_invalidate_pid(pid_t pid)
{
    if (psutil_proc_name_cache.pid == pid) {
        psutil_proc_name_cache.is_valid = 0;
    }

    if (psutil_proc_ppid_cache.pid == pid) {
        psutil_proc_ppid_cache.is_valid = 0;
    }

    if (psutil_proc_status_cache.pid == pid) {
        psutil_proc_status_cache.is_valid = 0;
    }
}

/*
 * Invalidate all cache entries
 */
void
psutil_cache_invalidate_all(void)
{
    psutil_proc_name_cache.is_valid = 0;
    psutil_proc_name_cache.pid = 0;
    psutil_proc_name_cache.data[0] = '\0';
    psutil_proc_name_cache.cache_time = 0;

    psutil_proc_ppid_cache.is_valid = 0;
    psutil_proc_ppid_cache.pid = 0;
    psutil_proc_ppid_cache.data = 0;
    psutil_proc_ppid_cache.cache_time = 0;

    psutil_proc_status_cache.is_valid = 0;
    psutil_proc_status_cache.pid = 0;
    psutil_proc_status_cache.data[0] = '\0';
    psutil_proc_status_cache.cache_time = 0;
}

/*
 * Cygwin-specific PID range check - Python wrapper
 * This checks if PID is valid and optionally if process exists
 */
PyObject *
psutil_check_pid_range_cygwin(PyObject *self, PyObject *args)
{
    pid_t pid;

    if (!PyArg_ParseTuple(args, _Py_PARSE_PID, &pid))
        return NULL;

    if (pid <= 0) {
        PyErr_SetString(PyExc_ValueError, "pid must be a positive integer (>0)");
        return NULL;
    }

    // Additional Cygwin-specific validation
    if (!psutil_cygwin_check_pid_range(pid)) {
        PyErr_SetString(PyExc_ValueError, "pid outside valid range for Cygwin");
        return NULL;
    }

    Py_RETURN_NONE;
}
