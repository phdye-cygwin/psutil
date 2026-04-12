/*
 * Copyright (c) 2025, Anthony Catel <contact@anthonycatel.com>
 * Copyright (c) 2025, Giampaolo Rodola
 * All rights reserved.
 * Use of this source code is governed by a BSD-style license.
 */

/*
System-wide process related functions for Cygwin.
MEMORY LEAK FIX: Updated proc_name(), proc_exe(), proc_ppid(), proc_create_time(),
proc_status(), and pid_exists_py() to use process locking pattern that prevents
the 1.2MB per call memory leaks.
*/

// Prevent _POSIX_C_SOURCE redefinition warning
#ifdef _POSIX_C_SOURCE
#undef _POSIX_C_SOURCE
#endif
#define _POSIX_C_SOURCE 200809L

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/param.h>
#include <sys/mount.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <strings.h>  // For strcasecmp
#include <unistd.h>
#include <time.h>
#include <ctype.h>    // For isspace
#include <signal.h>   // For kill, SIGSTOP, etc.
#include <dirent.h>   // For DIR, struct dirent, opendir, readdir, closedir

// Define WINVER before including windows.h to ensure external_pinfo is available
#ifndef WINVER
#define WINVER 0x0A00  // Windows 10
#endif
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0A00  // Windows 10
#endif

#include <windows.h>      // Must come before sys/cygwin.h for Windows types

// Ensure __CYGWIN__ is defined (should be set by compiler, but be explicit)
#ifndef __CYGWIN__
#define __CYGWIN__ 1
#endif

#include <sys/cygwin.h>   // For cygwin_internal and external_pinfo

#include <Python.h>
#include "../../arch/all/init.h"    // For common psutil functions
#include "init.h"  // For Cygwin-specific declarations

// Maximum possible path length under NT
#ifndef NT_MAX_PATH
#define NT_MAX_PATH 32767
#endif

// == ==================
// MAIN FUNCTIONS USING CYGWIN INTERNAL API
// == ==================

/*
 * Return a Python list of all the PIDs running on the system.
 * This function uses the CORRECT pattern and does NOT leak memory.
 */
PyObject *
psutil_pids(PyObject *self, PyObject *args)
{
    struct external_pinfo *p;
    PyObject *py_retlist = PyList_New(0);
    PyObject *py_pid = NULL;
    int lock_result;

    if (py_retlist == NULL)
        return NULL;

    // Lock process info during enumeration with timeout
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        // Lock failed - return empty list rather than blocking
        return py_retlist;
    }

    // Iterate through all processes using Cygwin internal API
    // IMPORTANT: The external_pinfo pointer returned by CW_GETPINFO
    // points to Cygwin's internal process table and should NOT be freed
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        // Create Python integer for PID
        py_pid = PyLong_FromLong(p->pid);
        if (!py_pid)
            goto error;

        // Add to list
        if (PyList_Append(py_retlist, py_pid))
            goto error;

        // Clear reference immediately to avoid accumulating references
        Py_DECREF(py_pid);
        py_pid = NULL;

        // Note: We do NOT free 'p' as it points to Cygwin's internal data
    }

    // Unlock process info
    cygwin_internal(CW_UNLOCK_PINFO);
    return py_retlist;

error:
    Py_XDECREF(py_pid);
    Py_DECREF(py_retlist);
    cygwin_internal(CW_UNLOCK_PINFO);
    return NULL;
}

/*
 * Get command arguments for a process as a Python list
 * Uses /proc/PID/cmdline - this function was NOT leaking
 */
PyObject *
psutil_proc_cmdline(PyObject *self, PyObject *args)
{
    long pid;
    char path[100];
    FILE *f = NULL;
    char *line = NULL;
    size_t size = 0;
    PyObject *py_retlist = PyList_New(0);
    PyObject *py_arg = NULL;
    ssize_t read_result;

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    if (!py_retlist)
        return NULL;

    sprintf(path, "/proc/%ld/cmdline", pid);
    f = fopen(path, "rb");
    if (!f) {
        psutil_debug("fopen(%s) -> %s", path, strerror(errno));
        if ((errno == ENOENT) || (errno == ESRCH) || (errno == EPERM) || (errno == EACCES)) {
            return py_retlist;  // Return empty list
        }
        psutil_PyErr_SetFromOSErrnoWithSyscall("fopen");
        goto error;
    }

    // Read the whole file - getdelim allocates memory for us
    while ((read_result = getdelim(&line, &size, '\0', f)) != -1) {
        py_arg = PyUnicode_DecodeFSDefault(line);
        if (!py_arg)
            goto error;
        if (PyList_Append(py_retlist, py_arg))
            goto error;
        Py_DECREF(py_arg);  // Release reference immediately
        py_arg = NULL;
    }

    if (ferror(f)) {
        psutil_PyErr_SetFromOSErrnoWithSyscall("getdelim");
        goto error;
    }

    // Clean up allocated memory
    if (line) {
        free(line);
        line = NULL;
    }
    fclose(f);
    return py_retlist;

error:
    if (line) free(line);
    if (f) fclose(f);
    Py_XDECREF(py_arg);
    Py_XDECREF(py_retlist);
    return NULL;
}

/*
 * Get process name using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_proc_name(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    char pname[NT_MAX_PATH + sizeof(" <defunct>") + 1];
    PyObject *result = NULL;
    int lock_result;

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        // Lock failed - this is an error condition
        PyErr_SetString(PyExc_OSError, "Failed to lock Cygwin process table");
        return NULL;
    }

    // Iterate through all processes using the WORKING pattern (CW_NEXTPID flag)
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        // Check if this is the process we're looking for
        if (p->pid == target_pid) {
            // Found the target process - extract name using existing logic
            if (p->ppid) {
                char *s;
                pname[0] = '\0';

                // Use safe string operations
                strncpy(pname, p->progname_long, NT_MAX_PATH);
                pname[NT_MAX_PATH] = '\0';  // Ensure null termination

                s = strrchr(pname, '.');
                if (s && strcasecmp(s, ".exe") == 0)
                    *s = '\0';

                if (p->process_state & PID_EXITED || (p->exitcode & ~0xffff))
                    strncat(pname, " <defunct>", sizeof(pname) - strlen(pname) - 1);
            }
            else {
                strncpy(pname, p->dwProcessId == 4 ? "System" : "*** unknown ***", sizeof(pname) - 1);
                pname[sizeof(pname) - 1] = '\0';
            }

            result = PyUnicode_DecodeFSDefault(pname);
            break;  // Found target process, exit loop
        }
    }

    // ALWAYS unlock the process table
    cygwin_internal(CW_UNLOCK_PINFO);

    // If we didn't find the process, return appropriate error
    if (!result) {
        NoSuchProcess("cygwin_internal(CW_GETPINFO) - process not found");
        return NULL;
    }

    return result;
}

/*
 * Get parent process ID using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_proc_ppid(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    PyObject *result = NULL;
    int lock_result;

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        PyErr_SetString(PyExc_OSError, "Failed to lock Cygwin process table");
        return NULL;
    }

    // Iterate through all processes using the WORKING pattern
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        if (p->pid == target_pid) {
            result = PyLong_FromLong(p->ppid);
            break;
        }
    }

    cygwin_internal(CW_UNLOCK_PINFO);

    if (!result) {
        NoSuchProcess("cygwin_internal(CW_GETPINFO) - process not found");
        return NULL;
    }

    return result;
}

/*
 * Get process creation time using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_proc_create_time(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    PyObject *result = NULL;
    int lock_result;

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        PyErr_SetString(PyExc_OSError, "Failed to lock Cygwin process table");
        return NULL;
    }

    // Iterate through all processes using the WORKING pattern
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        if (p->pid == target_pid) {
            result = PyFloat_FromDouble((double)p->start_time);
            break;
        }
    }

    cygwin_internal(CW_UNLOCK_PINFO);

    if (!result) {
        NoSuchProcess("cygwin_internal(CW_GETPINFO) - process not found");
        return NULL;
    }

    return result;
}

/*
 * Get process executable path using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_proc_exe(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    char exe_path[NT_MAX_PATH + 1];
    PyObject *result = NULL;
    int lock_result;

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        PyErr_SetString(PyExc_OSError, "Failed to lock Cygwin process table");
        return NULL;
    }

    // Iterate through all processes using the WORKING pattern (CW_NEXTPID flag)
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        // Check if this is the process we're looking for
        if (p->pid == target_pid) {
            // Found the target process - extract executable path
            if (p->ppid && p->progname_long[0]) {
                strncpy(exe_path, p->progname_long, NT_MAX_PATH);
                exe_path[NT_MAX_PATH] = '\0';
                result = PyUnicode_DecodeFSDefault(exe_path);
            } else {
                // No executable path available
                result = PyUnicode_FromString("");
            }
            break;  // Found target process, exit loop
        }
    }

    // ALWAYS unlock the process table
    cygwin_internal(CW_UNLOCK_PINFO);

    // If we didn't find the process, return appropriate error
    if (!result) {
        NoSuchProcess("cygwin_internal(CW_GETPINFO) - process not found");
        return NULL;
    }

    return result;
}

/*
 * Get process current working directory
 * Uses /proc/PID/cwd symlink - this function was NOT leaking
 */
PyObject *
psutil_proc_cwd(PyObject *self, PyObject *args)
{
    long pid;
    char path[100];
    char *buf = NULL;
    size_t buf_size = 4096;
    ssize_t len;
    PyObject *result;

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    buf = malloc(buf_size);
    if (!buf) {
        PyErr_NoMemory();
        return NULL;
    }

    sprintf(path, "/proc/%ld/cwd", pid);

    len = readlink(path, buf, buf_size - 1);
    if (len == -1) {
        free(buf);
        if ((errno == ENOENT) || (errno == ESRCH) || (errno == EPERM) || (errno == EACCES)) {
            NoSuchProcess("readlink -> ENOENT");
        } else {
            PyErr_SetFromErrno(PyExc_OSError);
        }
        return NULL;
    }

    buf[len] = '\0';
    result = PyUnicode_DecodeFSDefault(buf);
    free(buf);
    return result;
}

/*
 * Get process environment variables as a Python dictionary
 * Uses /proc/PID/environ - this function was NOT leaking
 */
PyObject *
psutil_proc_environ(PyObject *self, PyObject *args)
{
    long pid;
    char path[100];
    FILE *f = NULL;
    char *data = NULL;
    size_t size = 0;
    PyObject *py_retdict = PyDict_New();
    PyObject *py_key = NULL;
    PyObject *py_val = NULL;
    ssize_t read_result;

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    if (!py_retdict)
        return NULL;

    sprintf(path, "/proc/%ld/environ", pid);
    f = fopen(path, "rb");
    if (!f) {
        psutil_debug("fopen(%s) -> %s", path, strerror(errno));
        if ((errno == ENOENT) || (errno == ESRCH) || (errno == EPERM) || (errno == EACCES)) {
            return py_retdict;  // Return empty dict
        }
        psutil_PyErr_SetFromOSErrnoWithSyscall("fopen");
        goto error;
    }

    // Read environment variables
    while ((read_result = getdelim(&data, &size, '\0', f)) != -1) {
        char *equals = strchr(data, '=');
        if (equals) {
            *equals = '\0';
            py_key = PyUnicode_DecodeFSDefault(data);
            py_val = PyUnicode_DecodeFSDefault(equals + 1);
            if (!py_key || !py_val)
                goto error;
            if (PyDict_SetItem(py_retdict, py_key, py_val) < 0)
                goto error;
            Py_DECREF(py_key);  // Release references immediately
            Py_DECREF(py_val);
            py_key = NULL;
            py_val = NULL;
        }
    }

    if (ferror(f)) {
        psutil_PyErr_SetFromOSErrnoWithSyscall("getdelim");
        goto error;
    }

    if (data) {
        free(data);
        data = NULL;
    }
    fclose(f);
    return py_retdict;

error:
    if (data) free(data);
    if (f) fclose(f);
    Py_XDECREF(py_key);
    Py_XDECREF(py_val);
    Py_XDECREF(py_retdict);
    return NULL;
}

/*
 * Get process status using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_proc_status(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    PyObject *result = NULL;
    int lock_result;
    int status = 0;  // Default to running

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        PyErr_SetString(PyExc_OSError, "Failed to lock Cygwin process table");
        return NULL;
    }

    // Iterate through all processes using the WORKING pattern
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        if (p->pid == target_pid) {
            // Map Cygwin process states to psutil status codes
            if (p->process_state & PID_STOPPED)
                status = 5;  // STATUS_STOPPED
            else if (p->process_state & PID_TTYIN || p->process_state & PID_TTYOU)
                status = 1;  // STATUS_SLEEPING
            else if (p->process_state & PID_EXITED)
                status = 8;  // STATUS_ZOMBIE
            else
                status = 0;  // STATUS_RUNNING

            result = PyLong_FromLong(status);
            break;
        }
    }

    cygwin_internal(CW_UNLOCK_PINFO);

    if (!result) {
        NoSuchProcess("cygwin_internal(CW_GETPINFO) - process not found");
        return NULL;
    }

    return result;
}

/*
 * Get process thread count
 * Uses /proc/PID/stat - this function was NOT leaking
 */
PyObject *
psutil_proc_num_threads(PyObject *self, PyObject *args)
{
    long pid;
    char path[100];
    FILE *f;
    int num_threads = 1;  // Default to 1

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    // Try to get thread count from /proc/PID/stat
    sprintf(path, "/proc/%ld/stat", pid);
    f = fopen(path, "r");
    if (f) {
        // Skip to the num_threads field (field 20)
        char buffer[4096];
        if (fgets(buffer, sizeof(buffer), f)) {
            // Parse the stat file to get num_threads
            // This is a simplified parser - may need improvement
            char *p = strrchr(buffer, ')');
            if (p) {
                p += 2;  // Skip ") "
                int field = 3;  // We're at field 3 after the command name
                while (field < 20 && p) {
                    p = strchr(p, ' ');
                    if (p) p++;
                    field++;
                }
                if (p) {
                    sscanf(p, "%d", &num_threads);
                }
            }
        }
        fclose(f);
    }

    return PyLong_FromLong(num_threads);
}

/*
 * Get process open files
 * Uses /proc/PID/fd - this function was NOT leaking
 */
PyObject *
psutil_proc_open_files(PyObject *self, PyObject *args)
{
    long pid;
    char path[256];
    char link_path[4096];
    DIR *dirp;
    struct dirent *entry;
    PyObject *py_retlist = PyList_New(0);
    PyObject *py_tuple = NULL;
    PyObject *py_path = NULL;
    PyObject *py_fd = NULL;
    ssize_t len;

    if (! PyArg_ParseTuple(args, "l", &pid))
        return NULL;

    if (!py_retlist)
        return NULL;

    sprintf(path, "/proc/%ld/fd", pid);
    dirp = opendir(path);
    if (!dirp) {
        // Process doesn't exist or no permission
        return py_retlist;  // Return empty list
    }

    while ((entry = readdir(dirp)) != NULL) {
        if (strcmp(entry->d_name, ".") == 0 || strcmp(entry->d_name, "..") == 0)
            continue;

        // Build path to fd symlink
        snprintf(link_path, sizeof(link_path), "%s/%s", path, entry->d_name);

        // Read the symlink
        char target[4096];
        len = readlink(link_path, target, sizeof(target) - 1);
        if (len > 0) {
            target[len] = '\0';

            // Only include regular files (not sockets, pipes, etc.)
            if (target[0] == '/') {
                py_path = PyUnicode_DecodeFSDefault(target);
                py_fd = PyLong_FromString(entry->d_name, NULL, 10);

                if (!py_path || !py_fd)
                    goto error;

                py_tuple = PyTuple_Pack(2, py_path, py_fd);
                if (!py_tuple)
                    goto error;

                if (PyList_Append(py_retlist, py_tuple) < 0)
                    goto error;

                Py_DECREF(py_tuple);
                Py_DECREF(py_path);
                Py_DECREF(py_fd);
                py_tuple = NULL;
                py_path = NULL;
                py_fd = NULL;
            }
        }
    }

    closedir(dirp);
    return py_retlist;

error:
    closedir(dirp);
    Py_XDECREF(py_tuple);
    Py_XDECREF(py_path);
    Py_XDECREF(py_fd);
    Py_XDECREF(py_retlist);
    return NULL;
}

/*
 * Check if a process exists by PID using FIXED process locking pattern
 * MEMORY LEAK FIX: Use the same pattern as psutil_pids() which works correctly
 */
PyObject *
psutil_pid_exists_py(PyObject *self, PyObject *args)
{
    long target_pid;
    struct external_pinfo *p;
    int found = 0;
    int lock_result;

    if (!PyArg_ParseTuple(args, "l", &target_pid))
        return NULL;

    // Check if PID is valid
    if (target_pid <= 0) {
        return PyBool_FromLong(0);
    }

    // Use the working pattern from psutil_pids - LOCK the process table
    lock_result = (int)cygwin_internal(CW_LOCK_PINFO, 1000);
    if (lock_result == 0) {
        // If we can't lock, assume process doesn't exist
        return PyBool_FromLong(0);
    }

    // Iterate through all processes using the WORKING pattern
    for (int pid = 0;
         (p = (struct external_pinfo *) cygwin_internal(CW_GETPINFO, pid | CW_NEXTPID));
         pid = p->pid) {

        if (p->pid == target_pid) {
            found = 1;
            break;
        }
    }

    cygwin_internal(CW_UNLOCK_PINFO);

    return PyBool_FromLong(found);
}
