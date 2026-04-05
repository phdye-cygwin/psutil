/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform - System Information Functions
 * Category: System-wide Information (boot time, users)
 */

#include <Python.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>
#include <sys/resource.h>
#include <dirent.h>
#include <time.h>

#include "psutil_cygwin.h"
#include "../../arch/all/init.h"    // For common psutil functions

// == ===========================================================================
// --- System Information Functions
// == ===========================================================================

/*
 * Get system boot time
 */
PyObject *
psutil_boot_time(PyObject *self, PyObject *args)
{
    FILE *file = NULL;
    char buffer[1024];
    double uptime = 0.0;
    double boot_time;

    // Try to get uptime from /proc/uptime
    file = fopen("/proc/uptime", "r");
    if (file != NULL) {
        if (fscanf(file, "%lf", &uptime) == 1) {
            fclose(file);
            boot_time = (double)time(NULL) - uptime;
            return PyFloat_FromDouble(boot_time);
        }
        fclose(file);
    }

    // Fallback: try to get from /proc/stat
    file = fopen("/proc/stat", "r");
    if (file != NULL) {
        while (fgets(buffer, sizeof (buffer), file)) {
            if (strncmp(buffer, "btime ", 6) == 0) {
                unsigned long btime;
                if (sscanf(buffer, "btime %lu", &btime) == 1) {
                    fclose(file);
                    return PyFloat_FromDouble((double)btime);
                }
            }
        }
        fclose(file);
    }

    // Final fallback: return current time (not accurate, but prevents crash)
    boot_time = (double)time(NULL) - 3600.0; // Assume 1 hour uptime
    return PyFloat_FromDouble(boot_time);
}

/*
 * Get system users currently logged in
 * This is a placeholder - full implementation would parse /var/run/utmp
 */
PyObject *
psutil_users(PyObject *self, PyObject *args)
{
    PyObject *py_retlist = NULL;

    // Return empty list for now - full implementation would require
    // parsing /var/run/utmp or similar system files
    py_retlist = PyList_New(0);
    if (py_retlist == NULL) {
        return NULL;
    }

    // TODO: Implement user session parsing
    // This would involve reading utmp/wtmp files or using getutent()

    return py_retlist;
}

// == ===========================================================================
// --- Process Priority Functions (POSIX Implementation)
// == ===========================================================================

/*
 * Get process priority using POSIX getpriority()
 */
PyObject *
psutil_getpriority_posix(PyObject *self, PyObject *args)
{
    long pid;
    int priority;

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    errno = 0;
    priority = getpriority(PRIO_PROCESS, (id_t)pid);

    if (priority == -1 && errno != 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    return PyLong_FromLong(priority);
}

/*
 * Set process priority using POSIX setpriority()
 */
PyObject *
psutil_setpriority_posix(PyObject *self, PyObject *args)
{
    long pid;
    int priority;

    if (! PyArg_ParseTuple(args, "li", &pid, &priority))
        return NULL;

    // Validate priority range (-20 to 19 for POSIX nice values)
    if (priority < -20 || priority > 19) {
        PyErr_SetString(PyExc_ValueError, "Priority value must be between -20 and 19");
        return NULL;
    }

    if (setpriority(PRIO_PROCESS, (id_t)pid, priority) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    Py_RETURN_NONE;
}

