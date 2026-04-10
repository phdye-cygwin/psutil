/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform C extension - CPU Information Functions
 * Moved from phase2.c and phase3.c for better organization
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
#ifdef __CYGWIN__
#include <windows.h>
#include <sysinfoapi.h>
#endif

#include "psutil_cygwin.h"

// == ===========================================================================
// --- CPU Information Functions
// == ===========================================================================

// Get the number of logical CPUs
PyObject *
psutil_cpu_count_logical(PyObject *self, PyObject *args)
{
    long ncpus;

    // Try sysconf first
    ncpus = sysconf(_SC_NPROCESSORS_ONLN);
    if (ncpus != -1) {
        return Py_BuildValue("i", (int)ncpus);
    }

    // Fallback: count processors in /proc/cpuinfo
    FILE *file = fopen("/proc/cpuinfo", "r");
    if (file != NULL) {
        char buffer[1024];
        int count = 0;

        while (fgets(buffer, sizeof (buffer), file)) {
            if (strncmp(buffer, "processor", 9) == 0) {
                count++;
            }
        }
        fclose(file);

        if (count > 0) {
            return Py_BuildValue("i", count);
        }
    }

#ifdef __CYGWIN__
    // Windows fallback
    SYSTEM_INFO sysinfo;
    GetSystemInfo(&sysinfo);
    return Py_BuildValue("i", (int)sysinfo.dwNumberOfProcessors);
#endif

    PyErr_SetString(PyExc_RuntimeError, "Unable to determine logical CPU count");
    return NULL;
}

// Parse /proc/cpuinfo counting unique (physical_id, core_id) pairs.
// Each unique pair identifies one physical core; hyperthreading places
// multiple logical CPUs under the same pair, so deduplication yields
// the physical core count.
//
// The earlier implementation multiplied `physical_cores * cpu_cores`,
// which breaks inside hypervisors that leak the host CPU's topology
// via CPUID: `cpu cores` then reports the host's physical cores (e.g.
// 16) while the VM only has four logical CPUs assigned, giving
// logical=4 and "cores"=16 — impossible.
static int
parse_proc_cpuinfo_cores(void)
{
    FILE *file = NULL;
    char buffer[1024];
    char key[64], value[256];

#define MAX_CORE_PAIRS 256
    unsigned int pairs[MAX_CORE_PAIRS];
    int pair_count = 0;
    int current_physical_id = -1;
    int current_core_id = -1;

    file = fopen("/proc/cpuinfo", "r");
    if (file == NULL) {
        return -1;
    }

    while (fgets(buffer, sizeof (buffer), file)) {
        // Record the current (physical_id, core_id) pair when we hit a
        // blank line or the start of a new "processor" entry.
        if (buffer[0] == '\n' ||
            (strncmp(buffer, "processor", 9) == 0 &&
             (buffer[9] == '\t' || buffer[9] == ' ' || buffer[9] == ':'))) {
            if (current_physical_id >= 0 && current_core_id >= 0) {
                unsigned int pair =
                    ((unsigned)current_physical_id << 16) |
                    (unsigned)(current_core_id & 0xFFFF);
                int found = 0;
                for (int i = 0; i < pair_count; i++) {
                    if (pairs[i] == pair) { found = 1; break; }
                }
                if (!found && pair_count < MAX_CORE_PAIRS) {
                    pairs[pair_count++] = pair;
                }
            }
            current_physical_id = -1;
            current_core_id = -1;
            continue;
        }

        if (sscanf(buffer, "%63[^:]: %255[^\n]", key, value) == 2) {
            // Trim whitespace from key
            char *key_trimmed = key;
            while (*key_trimmed == ' ' || *key_trimmed == '\t') key_trimmed++;
            char *key_end = key_trimmed + strlen(key_trimmed) - 1;
            while (key_end > key_trimmed && (*key_end == ' ' || *key_end == '\t')) {
                *key_end = '\0';
                key_end--;
            }

            if (strcmp(key_trimmed, "physical id") == 0) {
                current_physical_id = atoi(value);
            }
            else if (strcmp(key_trimmed, "core id") == 0) {
                current_core_id = atoi(value);
            }
        }
    }

    // Flush the last entry (file may not end with a blank line).
    if (current_physical_id >= 0 && current_core_id >= 0) {
        unsigned int pair =
            ((unsigned)current_physical_id << 16) |
            (unsigned)(current_core_id & 0xFFFF);
        int found = 0;
        for (int i = 0; i < pair_count; i++) {
            if (pairs[i] == pair) { found = 1; break; }
        }
        if (!found && pair_count < MAX_CORE_PAIRS) {
            pairs[pair_count++] = pair;
        }
    }

    fclose(file);

    return pair_count > 0 ? pair_count : -1;
#undef MAX_CORE_PAIRS
}

#ifdef __CYGWIN__
// Count physical cores via GetLogicalProcessorInformationEx, which
// reports the cores actually visible to the calling process and is
// correct under hypervisor/VM isolation (unlike /proc/cpuinfo, which
// mirrors CPUID and can leak host topology).
static int
win32_cpu_count_cores(void)
{
    DWORD bufsize = 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore, NULL, &bufsize);
    if (GetLastError() != ERROR_INSUFFICIENT_BUFFER || bufsize == 0) {
        return -1;
    }
    SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *buf =
        (SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *)malloc(bufsize);
    if (buf == NULL) {
        return -1;
    }
    if (!GetLogicalProcessorInformationEx(RelationProcessorCore, buf, &bufsize)) {
        free(buf);
        return -1;
    }
    int cores = 0;
    DWORD offset = 0;
    while (offset < bufsize) {
        SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *info =
            (SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX *)((char *)buf + offset);
        if (info->Relationship == RelationProcessorCore) {
            cores++;
        }
        if (info->Size == 0) break;  // guard against malformed output
        offset += info->Size;
    }
    free(buf);
    return cores > 0 ? cores : -1;
}
#endif

// Get the number of physical CPU cores
PyObject *
psutil_cpu_count_cores(PyObject *self, PyObject *args)
{
    int cores;

#ifdef __CYGWIN__
    // Primary: Windows API, authoritative under virtualization.
    cores = win32_cpu_count_cores();
    if (cores > 0) {
        return Py_BuildValue("i", cores);
    }
#endif

    // Fallback: parse /proc/cpuinfo counting unique (physical, core) pairs.
    cores = parse_proc_cpuinfo_cores();
    if (cores > 0) {
        return Py_BuildValue("i", cores);
    }

    // Return None if we can't determine core count
    Py_INCREF(Py_None);
    return Py_None;
}

// Parse /proc/stat to get per-CPU times
static PyObject *
parse_proc_stat_cpu_times(void)
{
    FILE *file = NULL;
    char buffer[1024];
    PyObject *py_retlist = NULL;
    PyObject *py_cputimes = NULL;

    file = fopen("/proc/stat", "r");
    if (file == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    py_retlist = PyList_New(0);
    if (py_retlist == NULL) {
        fclose(file);
        return NULL;
    }

    while (fgets(buffer, sizeof (buffer), file)) {
        if (strncmp(buffer, "cpu", 3) == 0 && buffer[3] >= '0' && buffer[3] <= '9') {
            // Parse individual CPU line
            unsigned long long user, nice, system, idle, iowait = 0, irq = 0, softirq = 0, steal = 0;

            int parsed = sscanf(buffer, "cpu%*d %llu %llu %llu %llu %llu %llu %llu %llu",
                              &user, &nice, &system, &idle, &iowait, &irq, &softirq, &steal);

            if (parsed >= 4) {
                // Convert from USER_HZ to seconds
                long ticks_per_sec = sysconf(_SC_CLK_TCK);
                if (ticks_per_sec <= 0) ticks_per_sec = 100;

                double user_sec = (double)user / ticks_per_sec;
                double nice_sec = (double)nice / ticks_per_sec;
                double system_sec = (double)system / ticks_per_sec;
                double idle_sec = (double)idle / ticks_per_sec;
                double iowait_sec = (parsed > 4) ? (double)iowait / ticks_per_sec : 0.0;
                double irq_sec = (parsed > 5) ? (double)irq / ticks_per_sec : 0.0;
                double softirq_sec = (parsed > 6) ? (double)softirq / ticks_per_sec : 0.0;
                double steal_sec = (parsed > 7) ? (double)steal / ticks_per_sec : 0.0;

                py_cputimes = Py_BuildValue("(dddddddd)",
                                          user_sec, nice_sec, system_sec, idle_sec,
                                          iowait_sec, irq_sec, softirq_sec, steal_sec);

                if (py_cputimes == NULL)
                    goto error;

                if (PyList_Append(py_retlist, py_cputimes) < 0) {
                    Py_DECREF(py_cputimes);
                    goto error;
                }

                Py_DECREF(py_cputimes);
            }
        }
    }

    fclose(file);
    return py_retlist;

error:
    if (file) fclose(file);
    Py_XDECREF(py_retlist);
    return NULL;
}

// Get per-CPU times
PyObject *
psutil_per_cpu_times(PyObject *self, PyObject *args)
{
    return parse_proc_stat_cpu_times();
}

// Get system-wide CPU times (sum of all CPUs)
PyObject *
psutil_cpu_times(PyObject *self, PyObject *args)
{
    FILE *file = NULL;
    char buffer[1024];
    unsigned long long user = 0, nice = 0, system = 0, idle = 0;
    unsigned long long iowait = 0, irq = 0, softirq = 0, steal = 0;

    file = fopen("/proc/stat", "r");
    if (file == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    // Read first line which contains aggregated CPU stats
    if (fgets(buffer, sizeof (buffer), file)) {
        if (strncmp(buffer, "cpu ", 4) == 0) {
            int parsed = sscanf(buffer, "cpu %llu %llu %llu %llu %llu %llu %llu %llu",
                              &user, &nice, &system, &idle, &iowait, &irq, &softirq, &steal);

            if (parsed >= 4) {
                // Convert from USER_HZ to seconds
                long ticks_per_sec = sysconf(_SC_CLK_TCK);
                if (ticks_per_sec <= 0) ticks_per_sec = 100;

                double user_sec = (double)user / ticks_per_sec;
                double nice_sec = (double)nice / ticks_per_sec;
                double system_sec = (double)system / ticks_per_sec;
                double idle_sec = (double)idle / ticks_per_sec;
                double iowait_sec = (parsed > 4) ? (double)iowait / ticks_per_sec : 0.0;
                double irq_sec = (parsed > 5) ? (double)irq / ticks_per_sec : 0.0;
                double softirq_sec = (parsed > 6) ? (double)softirq / ticks_per_sec : 0.0;
                double steal_sec = (parsed > 7) ? (double)steal / ticks_per_sec : 0.0;

                fclose(file);
                return Py_BuildValue("(dddddddd)",
                                   user_sec, nice_sec, system_sec, idle_sec,
                                   iowait_sec, irq_sec, softirq_sec, steal_sec);
            }
        }
    }

    fclose(file);
    PyErr_SetString(PyExc_RuntimeError, "Unable to read CPU times from /proc/stat");
    return NULL;
}

// Get system CPU statistics
PyObject *
psutil_cpu_stats(PyObject *self, PyObject *args)
{
    FILE *file = NULL;
    char buffer[1024];
    unsigned long ctx_switches = 0, interrupts = 0, soft_interrupts = 0;

    file = fopen("/proc/stat", "r");
    if (file == NULL) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    // Parse /proc/stat for statistics
    while (fgets(buffer, sizeof (buffer), file)) {
        if (strncmp(buffer, "ctxt ", 5) == 0) {
            sscanf(buffer, "ctxt %lu", &ctx_switches);
        }
        else if (strncmp(buffer, "intr ", 5) == 0) {
            sscanf(buffer, "intr %lu", &interrupts);
        }
        else if (strncmp(buffer, "softirq ", 8) == 0) {
            sscanf(buffer, "softirq %lu", &soft_interrupts);
        }
    }

    fclose(file);

    // Return (ctx_switches, interrupts, soft_interrupts, syscalls)
    // Note: syscalls not available in /proc/stat, using 0
    return Py_BuildValue("(llll)",
                        (long)ctx_switches, (long)interrupts,
                        (long)soft_interrupts, (long)0);
}

// == ===========================================================================
// --- Process CPU Information Functions (moved from phase3.c)
// == ===========================================================================

/*
 * Get process CPU times from /proc/PID/stat
 * Returns tuple: (user_time, system_time, children_user_time, children_system_time)
 */
PyObject *
psutil_proc_cpu_times(PyObject *self, PyObject *args)
{
    pid_t pid;
    char path[PATH_MAX];
    FILE *file = NULL;
    char buffer[1024];
    char *ptr;
    int field;

    // CPU time values in clock ticks
    unsigned long long utime = 0, stime = 0, cutime = 0, cstime = 0;

    // Clock ticks per second
    static long ticks_per_sec = -1;

    if (!PyArg_ParseTuple(args, "i", &pid)) {
        return NULL;
    }

    // Initialize ticks per second if not done yet
    if (ticks_per_sec < 0) {
        ticks_per_sec = sysconf(_SC_CLK_TCK);
        if (ticks_per_sec <= 0) {
            ticks_per_sec = 100; // Default fallback
        }
    }

    snprintf(path, sizeof (path), "/proc/%d/stat", pid);
    file = fopen(path, "r");
    if (file == NULL) {
        if (errno == ENOENT) {
            return PyErr_Format(PyExc_ProcessLookupError, "process %d not found", pid);
        }
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    if (fgets(buffer, sizeof (buffer), file) != NULL) {
        // Parse /proc/PID/stat format:
        // Fields we need: utime (14), stime (15), cutime (16), cstime (17)
        // Format: pid (comm) state ppid ... utime stime cutime cstime ...

        // Find the end of comm field
        ptr = strrchr(buffer, ')');
        if (ptr != NULL) {
            ptr += 2; // Skip ") "

            // Parse fields after comm, we want fields 11-14 (utime, stime, cutime, cstime)
            // Fields: state ppid pgrp session tty_nr tpgid flags minflt cminflt majflt cmajflt
            //         utime stime cutime cstime ...
            for (field = 0; field < 11 && ptr != NULL; field++) {
                ptr = strchr(ptr, ' ');
                if (ptr != NULL) ptr++;
            }

            if (ptr != NULL && sscanf(ptr, "%llu %llu %llu %llu",
                                     &utime, &stime, &cutime, &cstime) == 4) {
                fclose(file);

                // Convert from clock ticks to seconds
                double user_sec = (double)utime / ticks_per_sec;
                double system_sec = (double)stime / ticks_per_sec;
                double children_user_sec = (double)cutime / ticks_per_sec;
                double children_system_sec = (double)cstime / ticks_per_sec;

                return Py_BuildValue("(dddd)",
                                    user_sec, system_sec,
                                    children_user_sec, children_system_sec);
            }
        }
    }

    fclose(file);
    return PyErr_Format(PyExc_ValueError, "invalid /proc/%d/stat format", pid);
}
