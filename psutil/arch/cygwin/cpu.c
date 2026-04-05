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

// Parse /proc/cpuinfo to get CPU core information
static int
parse_proc_cpuinfo_cores(void)
{
    FILE *file = NULL;
    char buffer[1024];
    char key[64], value[256];
    int physical_cores = 0;
    int last_physical_id = -1;
    int core_count = 0;

    file = fopen("/proc/cpuinfo", "r");
    if (file == NULL) {
        return -1;
    }

    while (fgets(buffer, sizeof (buffer), file)) {
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
                int physical_id = atoi(value);
                if (physical_id > last_physical_id) {
                    last_physical_id = physical_id;
                    physical_cores = physical_id + 1;
                }
            }
            else if (strcmp(key_trimmed, "cpu cores") == 0) {
                core_count = atoi(value);
            }
        }
    }

    fclose(file);

    // If we found physical CPU info, use cores per physical CPU
    if (physical_cores > 0 && core_count > 0) {
        return physical_cores * core_count;
    }

    return -1;
}

// Get the number of physical CPU cores
PyObject *
psutil_cpu_count_cores(PyObject *self, PyObject *args)
{
    int cores;

    // Try to parse from /proc/cpuinfo
    cores = parse_proc_cpuinfo_cores();
    if (cores > 0) {
        return Py_BuildValue("i", cores);
    }

    // Fallback: assume logical CPUs are the same as physical cores
    long ncpus = sysconf(_SC_NPROCESSORS_ONLN);
    if (ncpus != -1) {
        return Py_BuildValue("i", (int)ncpus);
    }

#ifdef __CYGWIN__
    // Windows fallback
    SYSTEM_INFO sysinfo;
    GetSystemInfo(&sysinfo);
    return Py_BuildValue("i", (int)sysinfo.dwNumberOfProcessors);
#endif

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
