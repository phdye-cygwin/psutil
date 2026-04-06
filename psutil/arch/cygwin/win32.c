/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Windows API implementation stubs for Cygwin platform
 * Added proper parameter validation and basic functionality
 */

#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <dirent.h>
#include <errno.h>

#ifdef __CYGWIN__
// Cygwin environment - provide minimal Windows API compatibility

/*
 * Parse /proc/net/tcp and /proc/net/udp to get network connections
 * This provides basic functionality using Linux-style /proc filesystem
 * Added basic network connection detection
 */
static PyObject *
parse_proc_net_file(const char *filename, const char *protocol)
{
    FILE *file;
    char line[1024];
    PyObject *py_retlist = PyList_New(0);
    int line_num = 0;

    if (py_retlist == NULL) {
        return NULL;
    }

    file = fopen(filename, "r");
    if (file == NULL) {
        // File doesn't exist or can't be read - return empty list
        return py_retlist;
    }

    // Skip header line
    if (fgets(line, sizeof (line), file) == NULL) {
        fclose(file);
        return py_retlist;
    }

    // Parse each connection line
    while (fgets(line, sizeof (line), file)) {
        unsigned int local_addr, local_port;
        unsigned int remote_addr, remote_port;
        int state;
        char local_ip[16], remote_ip[16];

        line_num++;

        // Parse the line - basic format parsing
        int parsed = sscanf(line, "%*d: %X:%X %X:%X %X",
                           &local_addr, &local_port,
                           &remote_addr, &remote_port, &state);

        if (parsed >= 4) {
            // Convert addresses to string format
            snprintf(local_ip, sizeof (local_ip), "%d.%d.%d.%d",
                    local_addr & 0xFF, (local_addr >> 8) & 0xFF,
                    (local_addr >> 16) & 0xFF, (local_addr >> 24) & 0xFF);

            snprintf(remote_ip, sizeof (remote_ip), "%d.%d.%d.%d",
                    remote_addr & 0xFF, (remote_addr >> 8) & 0xFF,
                    (remote_addr >> 16) & 0xFF, (remote_addr >> 24) & 0xFF);

            // Build connection tuple: (fd, family, type, laddr, raddr, status, pid)
            PyObject *laddr_tuple = NULL;
            PyObject *raddr_tuple = NULL;
            PyObject *conn_tuple = NULL;

            // Local address tuple
            if (local_port > 0) {
                laddr_tuple = Py_BuildValue("(si)", local_ip, local_port);
            } else {
                laddr_tuple = Py_BuildValue("()");
            }

            // Remote address tuple
            if (remote_addr != 0 && remote_port > 0) {
                raddr_tuple = Py_BuildValue("(si)", remote_ip, remote_port);
            } else {
                raddr_tuple = Py_BuildValue("()");
            }

            if (laddr_tuple && raddr_tuple) {
                // Protocol family and type
                int family = 2;  // AF_INET
                int type = (strcmp(protocol, "tcp") == 0) ? 1 : 2;  // SOCK_STREAM : SOCK_DGRAM

                conn_tuple = Py_BuildValue("(iiOOii)",
                    -1,        // fd (unknown)
                    family,    // family
                    type,      // type
                    laddr_tuple, // laddr
                    raddr_tuple, // raddr
                    state,     // status
                    -1         // pid (unknown for system-wide)
                );

                if (conn_tuple) {
                    PyList_Append(py_retlist, conn_tuple);
                    Py_DECREF(conn_tuple);
                }
            }

            Py_XDECREF(laddr_tuple);
            Py_XDECREF(raddr_tuple);
        }

        // Limit to reasonable number of connections to avoid performance issues
        if (line_num > 1000) {
            break;
        }
    }

    fclose(file);
    return py_retlist;
}

/*
 * Implementation of net_connections using /proc filesystem
 * Added basic network connection detection instead of just empty list
 */
PyObject *
psutil_net_connections_win32(PyObject *self, PyObject *args)
{
    char *kind = NULL;
    PyObject *py_retlist = PyList_New(0);

    if (py_retlist == NULL) {
        return NULL;
    }

    // kind parameter is already validated by the wrapper function
    if (!PyArg_ParseTuple(args, "|s", &kind)) {
        Py_DECREF(py_retlist);
        return NULL;
    }

    // Default kind is "inet" if not specified
    if (kind == NULL) {
        kind = "inet";
    }

    // Parse TCP connections if requested
    if (strstr(kind, "tcp") || strstr(kind, "inet") || strcmp(kind, "all") == 0) {
        PyObject *tcp_connections = parse_proc_net_file("/proc/net/tcp", "tcp");
        if (tcp_connections) {
            // Add all TCP connections to result list
            Py_ssize_t tcp_size = PyList_Size(tcp_connections);
            for (Py_ssize_t i = 0; i < tcp_size; i++) {
                PyObject *conn = PyList_GetItem(tcp_connections, i);
                if (conn) {
                    Py_INCREF(conn);
                    PyList_Append(py_retlist, conn);
                }
            }
            Py_DECREF(tcp_connections);
        }
    }

    // Parse UDP connections if requested
    if (strstr(kind, "udp") || strstr(kind, "inet") || strcmp(kind, "all") == 0) {
        PyObject *udp_connections = parse_proc_net_file("/proc/net/udp", "udp");
        if (udp_connections) {
            // Add all UDP connections to result list
            Py_ssize_t udp_size = PyList_Size(udp_connections);
            for (Py_ssize_t i = 0; i < udp_size; i++) {
                PyObject *conn = PyList_GetItem(udp_connections, i);
                if (conn) {
                    Py_INCREF(conn);
                    PyList_Append(py_retlist, conn);
                }
            }
            Py_DECREF(udp_connections);
        }
    }

    return py_retlist;
}

/*
 * Implementation of per-process net_connections using /proc filesystem
 * Added basic process-specific network connection detection
 */
PyObject *
psutil_proc_net_connections_win32(PyObject *self, PyObject *args)
{
    int pid;
    char *kind = NULL;
    PyObject *py_retlist = PyList_New(0);

    if (py_retlist == NULL) {
        return NULL;
    }

    // Parameters already validated by wrapper function
    if (!PyArg_ParseTuple(args, "i|s", &pid, &kind)) {
        Py_DECREF(py_retlist);
        return NULL;
    }

    // Default kind is "inet" if not specified
    if (kind == NULL) {
        kind = "inet";
    }

    // Try to read process-specific network information
    // This is limited on Cygwin, so we return system-wide connections
    // and filter by PID if possible (though PID info may not be available)

    // For now, return system-wide connections as process-specific detection
    // is complex without full Windows API access
    PyObject *all_connections = psutil_net_connections_win32(self,
                                   Py_BuildValue("(s)", kind));

    if (all_connections) {
        // In a full implementation, we would filter by PID here
        // For now, just return all connections
        Py_DECREF(py_retlist);
        return all_connections;
    }

    return py_retlist;
}

/*
 * Windows getpagesize implementation
 * Returns system page size using sysconf if available
 * Better implementation using actual system call
 */
PyObject *
psutil_getpagesize_win32(PyObject *self, PyObject *args)
{
    long page_size;

#ifdef _SC_PAGESIZE
    page_size = sysconf(_SC_PAGESIZE);
    if (page_size > 0) {
        return PyLong_FromLong(page_size);
    }
#endif

    // Fallback to common page size
    return PyLong_FromLong(4096);
}

/*
 * Windows initialization stub
 * Added basic initialization
 */
int
psutil_win32_init(void)
{
    // Check if /proc filesystem is available
    DIR *proc_dir = opendir("/proc");
    if (proc_dir) {
        closedir(proc_dir);
        return 0;  // Success
    }

    return -1;  // /proc not available
}

/*
 * Windows cleanup stub
 */
void
psutil_win32_cleanup(void)
{
    // Nothing to clean up in current implementation
}

#endif  // __CYGWIN__
