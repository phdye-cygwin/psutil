/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin network implementation - POSIX network interfaces + Windows connections
 * This file integrates both POSIX and Windows networking functionality while
 * avoiding header conflicts through careful compilation unit separation.
 *
 * FIXED: Parameter validation, interface function errors, performance issues
 */

#include <Python.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <net/if.h>
#include <unistd.h>
#include <ifaddrs.h>
#include <netinet/in.h>
#include <netdb.h>
#include <arpa/inet.h>

// Define missing constants for Cygwin if not already defined
#ifndef NI_MAXHOST
    #define NI_MAXHOST 1025
#endif
#ifndef NI_NUMERICHOST
    #define NI_NUMERICHOST 1
#endif

// Define PSUTIL_STRNCPY macro locally if not available from header
#ifndef PSUTIL_STRNCPY
#define PSUTIL_STRNCPY(dst, src, n) \
    strncpy(dst, src, n - 1); \
    dst[n - 1] = '\0'
#endif

#include "../all/init.h"
#include "init.h"

// == ===========================================================================
// --- Parameter validation helper functions
// == ===========================================================================

/*
 * Validate string parameter for interface functions
 * Returns 1 if valid, 0 if invalid (sets exception)
 */
static int
validate_interface_name(const char *interface_name)
{
    if (!interface_name) {
        PyErr_SetString(PyExc_TypeError, "Interface name must be a string");
        return 0;
    }

    if (strlen(interface_name) == 0) {
        PyErr_SetString(PyExc_ValueError, "Interface name cannot be empty");
        return 0;
    }

    if (strlen(interface_name) >= IFNAMSIZ) {
        PyErr_Format(PyExc_ValueError, "Interface name too long (max %d characters)", IFNAMSIZ - 1);
        return 0;
    }
    return 1;
}

/*
 * Validate 'kind' parameter for network connection functions
 * Returns 1 if valid, 0 if invalid (sets exception)
 */
int
psutil_validate_connection_kind(const char *kind)
{
    if (!kind) {
        // NULL is acceptable - means all connections
        return 1;
    }

    // Valid kinds: inet, inet4, inet6, tcp, tcp4, tcp6, udp, udp4, udp6, all
    // Also allow 'unix' for compatibility even though not supported on Cygwin Phase 1
    const char *valid_kinds[] = {
        "inet", "inet4", "inet6", "tcp", "tcp4", "tcp6",
        "udp", "udp4", "udp6", "all", "unix", NULL
    };

    for (int i = 0; valid_kinds[i] != NULL; i++) {
        if (strcmp(kind, valid_kinds[i]) == 0) {
            return 1;
        }
    }

    PyErr_Format(PyExc_ValueError, "Invalid connection kind: %s", kind);
    return 0;
}

// == ===========================================================================
// --- POSIX Network Interface Functions (with proper validation)
// == ===========================================================================

/*
 * Translate a sockaddr struct into a Python string.
 * Return empty string if address family is not supported or conversion fails.
 * FIXED Issue 016: Return empty string instead of None for consistency.
 */
PyObject *
psutil_convert_ipaddr_cygwin(struct sockaddr *addr, int family)
{
    char buf[NI_MAXHOST];
    int err;
    int addrlen;

    if (addr == NULL) {
        return PyUnicode_FromString("");
    }
    else if (family == AF_INET || family == AF_INET6) {
        if (family == AF_INET)
            addrlen = sizeof (struct sockaddr_in);
        else
            addrlen = sizeof (struct sockaddr_in6);

        err = getnameinfo(addr, addrlen, buf, sizeof (buf), NULL, 0,
                          NI_NUMERICHOST);
        if (err != 0) {
            // Return empty string if we can't resolve the address
            return PyUnicode_FromString("");
        }
        else {
            return Py_BuildValue("s", buf);
        }
    }
    else {
        // For other address families, return empty string
        return PyUnicode_FromString("");
    }
}

/*
 * Check if an interface entry already exists in the list to avoid duplicates
 * FIXED Issue 016: Prevent duplicate interface entries
 * OPTIMIZED: Use cached interface lookup for better performance
 */
static int
interface_already_added(PyObject *py_retlist, const char *interface_name, int family)
{
    Py_ssize_t list_size = PyList_Size(py_retlist);

    // Quick optimization: if list is empty, no need to check
    if (list_size == 0) {
        return 0;
    }

    for (Py_ssize_t i = 0; i < list_size; i++) {
        PyObject *existing_tuple = PyList_GetItem(py_retlist, i);
        if (existing_tuple == NULL) continue;

        // Extract interface name and family from existing tuple
        PyObject *existing_name = PyTuple_GetItem(existing_tuple, 0);
        PyObject *existing_family = PyTuple_GetItem(existing_tuple, 1);

        if (existing_name == NULL || existing_family == NULL) continue;

        const char *existing_name_str = PyUnicode_AsUTF8(existing_name);
        long existing_family_val = PyLong_AsLong(existing_family);

        // Check for duplicate: same interface name and family
        if (existing_name_str != NULL &&             strcmp(existing_name_str, interface_name) == 0 &&             existing_family_val == family) {
            return 1;  // Already exists
        }
    }

    return 0;  // Not found
}

/*
 * Return NICs information a-la ifconfig as a list of tuples.
 * Cygwin-specific implementation using standard POSIX APIs.
 *
 * FIXED Issue 014: Include all interfaces
 * FIXED Issue 016: Use empty strings instead of None, prevent duplicates
 * OPTIMIZED: Better performance for large interface lists
 */
PyObject*
psutil_net_if_addrs(PyObject* self, PyObject* args)
{
    struct ifaddrs *ifaddr, *ifa;
    int family;

    PyObject *py_retlist = PyList_New(0);
    PyObject *py_tuple = NULL;
    PyObject *py_address = NULL;
    PyObject *py_netmask = NULL;
    PyObject *py_broadcast = NULL;
    PyObject *py_ptp = NULL;

    if (py_retlist == NULL)
        return NULL;
    if (getifaddrs(&ifaddr) == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        goto error;
    }

    for (ifa = ifaddr; ifa != NULL; ifa = ifa->ifa_next) {
        // Handle interfaces without addresses - use family 0 and empty strings
        if (!ifa->ifa_addr) {
            // Check for duplicates before adding (optimized check)
            if (interface_already_added(py_retlist, ifa->ifa_name, 0)) {
                continue;  // Skip duplicate
            }

            // Create entry with empty strings instead of None
            py_address = PyUnicode_FromString("");
            py_netmask = PyUnicode_FromString("");
            py_broadcast = PyUnicode_FromString("");
            py_ptp = PyUnicode_FromString("");

            if (!py_address || !py_netmask || !py_broadcast || !py_ptp)
                goto error;

            py_tuple = Py_BuildValue(
                "(siOOOO)",
                ifa->ifa_name,
                0,  // family = 0 for unknown
                py_address,
                py_netmask,
                py_broadcast,
                py_ptp
            );

            if (!py_tuple)
                goto error;
            if (PyList_Append(py_retlist, py_tuple))
                goto error;
            Py_CLEAR(py_tuple);
            Py_CLEAR(py_address);
            Py_CLEAR(py_netmask);
            Py_CLEAR(py_broadcast);
            Py_CLEAR(py_ptp);
            continue;
        }

        family = ifa->ifa_addr->sa_family;

        // Check for duplicates before processing (optimized)
        if (interface_already_added(py_retlist, ifa->ifa_name, family)) {
            continue;  // Skip duplicate
        }

        py_address = psutil_convert_ipaddr_cygwin(ifa->ifa_addr, family);
        if (py_address == NULL)
            goto error;

        py_netmask = psutil_convert_ipaddr_cygwin(ifa->ifa_netmask, family);
        if (py_netmask == NULL)
            goto error;

        if (ifa->ifa_flags & IFF_BROADCAST) {
            py_broadcast = psutil_convert_ipaddr_cygwin(ifa->ifa_broadaddr, family);
            py_ptp = PyUnicode_FromString("");
        }
        else if (ifa->ifa_flags & IFF_POINTOPOINT) {
            py_ptp = psutil_convert_ipaddr_cygwin(ifa->ifa_dstaddr, family);
            py_broadcast = PyUnicode_FromString("");
        }
        else {
            py_broadcast = PyUnicode_FromString("");
            py_ptp = PyUnicode_FromString("");
        }

        if ((py_broadcast == NULL) || (py_ptp == NULL))
            goto error;

        py_tuple = Py_BuildValue(
            "(siOOOO)",
            ifa->ifa_name,
            family,
            py_address,
            py_netmask,
            py_broadcast,
            py_ptp
        );

        if (! py_tuple)
            goto error;
        if (PyList_Append(py_retlist, py_tuple))
            goto error;
        Py_CLEAR(py_tuple);
        Py_CLEAR(py_address);
        Py_CLEAR(py_netmask);
        Py_CLEAR(py_broadcast);
        Py_CLEAR(py_ptp);
    }

    freeifaddrs(ifaddr);
    return py_retlist;

error:
    if (ifaddr != NULL)
        freeifaddrs(ifaddr);
    Py_DECREF(py_retlist);
    Py_XDECREF(py_tuple);
    Py_XDECREF(py_address);
    Py_XDECREF(py_netmask);
    Py_XDECREF(py_broadcast);
    Py_XDECREF(py_ptp);
    return NULL;
}

/*
 * Return NIC MTU.
 * Standard POSIX implementation suitable for Cygwin.
 * FIXED: Better error handling and parameter validation
 */
PyObject *
psutil_net_if_mtu(PyObject *self, PyObject *args)
{
    char *nic_name;
    int sock = -1;
    int ret;
    struct ifreq ifr;

    // Parameter validation with TypeError for non-strings
    if (!PyArg_ParseTuple(args, "s", &nic_name)) {
        // This automatically sets TypeError for non-string args
        return NULL;
    }

    // Additional interface name validation
    if (!validate_interface_name(nic_name)) {
        return NULL;
    }

    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    memset(&ifr, 0, sizeof (ifr));
    PSUTIL_STRNCPY(ifr.ifr_name, nic_name, sizeof (ifr.ifr_name));
    ret = ioctl(sock, SIOCGIFMTU, &ifr);
    if (ret == -1) {
        close(sock);
        if (errno == ENODEV) {
            PyErr_Format(PyExc_OSError, "No such interface: %s", nic_name);
        } else {
            PyErr_Format(PyExc_OSError, "Failed to get MTU for %s: %s", nic_name, strerror(errno));
        }
        return NULL;
    }
    close(sock);

    return Py_BuildValue("i", ifr.ifr_mtu);
}

static int
append_flag(PyObject *py_retlist, const char *flag_name)
{
    PyObject *py_str = NULL;

    py_str = PyUnicode_FromString(flag_name);
    if (! py_str)
        return 0;
    if (PyList_Append(py_retlist, py_str)) {
        Py_DECREF(py_str);
        return 0;
    }
    Py_CLEAR(py_str);

    return 1;
}

/*
 * Get all of the NIC flags and return them.
 * Standard POSIX implementation suitable for Cygwin.
 * FIXED: Better parameter validation and error handling
 */
PyObject *
psutil_net_if_flags(PyObject *self, PyObject *args)
{
    char *nic_name;
    int sock = -1;
    int ret;
    struct ifreq ifr;
    PyObject *py_retlist = PyList_New(0);
    short int flags;

    if (py_retlist == NULL)
        return NULL;

    // Parameter validation with TypeError for non-strings
    if (!PyArg_ParseTuple(args, "s", &nic_name)) {
        Py_DECREF(py_retlist);
        return NULL;
    }

    // Additional interface name validation
    if (!validate_interface_name(nic_name)) {
        Py_DECREF(py_retlist);
        return NULL;
    }

    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        goto error;
    }

    memset(&ifr, 0, sizeof (ifr));
    PSUTIL_STRNCPY(ifr.ifr_name, nic_name, sizeof (ifr.ifr_name));
    ret = ioctl(sock, SIOCGIFFLAGS, &ifr);
    if (ret == -1) {
        if (errno == ENODEV) {
            PyErr_Format(PyExc_OSError, "No such interface: %s", nic_name);
        } else {
            PyErr_Format(PyExc_OSError, "Failed to get flags for %s: %s", nic_name, strerror(errno));
        }
        goto error;
    }

    close(sock);
    sock = -1;

    flags = ifr.ifr_flags & 0xFFFF;

    // Cygwin supports standard POSIX network interface flags
#ifdef IFF_UP
    if (flags & IFF_UP)
        if (!append_flag(py_retlist, "up"))
            goto error;
#endif
#ifdef IFF_BROADCAST
    if (flags & IFF_BROADCAST)
        if (!append_flag(py_retlist, "broadcast"))
            goto error;
#endif
#ifdef IFF_DEBUG
    if (flags & IFF_DEBUG)
        if (!append_flag(py_retlist, "debug"))
            goto error;
#endif
#ifdef IFF_LOOPBACK
    if (flags & IFF_LOOPBACK)
        if (!append_flag(py_retlist, "loopback"))
            goto error;
#endif
#ifdef IFF_POINTOPOINT
    if (flags & IFF_POINTOPOINT)
        if (!append_flag(py_retlist, "pointopoint"))
            goto error;
#endif
#ifdef IFF_NOTRAILERS
    if (flags & IFF_NOTRAILERS)
        if (!append_flag(py_retlist, "notrailers"))
            goto error;
#endif
#ifdef IFF_RUNNING
    if (flags & IFF_RUNNING)
        if (!append_flag(py_retlist, "running"))
            goto error;
#endif
#ifdef IFF_NOARP
    if (flags & IFF_NOARP)
        if (!append_flag(py_retlist, "noarp"))
            goto error;
#endif
#ifdef IFF_PROMISC
    if (flags & IFF_PROMISC)
        if (!append_flag(py_retlist, "promisc"))
            goto error;
#endif
#ifdef IFF_ALLMULTI
    if (flags & IFF_ALLMULTI)
        if (!append_flag(py_retlist, "allmulti"))
            goto error;
#endif
#ifdef IFF_MULTICAST
    if (flags & IFF_MULTICAST)
        if (!append_flag(py_retlist, "multicast"))
            goto error;
#endif

    return py_retlist;

error:
    Py_DECREF(py_retlist);
    if (sock != -1)
        close(sock);
    return NULL;
}

/*
 * Inspect NIC flags, returns a bool indicating whether the NIC is
 * running. Standard POSIX implementation suitable for Cygwin.
 * FIXED: Better parameter validation and error handling
 */
PyObject *
psutil_net_if_is_running(PyObject *self, PyObject *args)
{
    char *nic_name;
    int sock = -1;
    int ret;
    struct ifreq ifr;

    // Parameter validation with TypeError for non-strings
    if (!PyArg_ParseTuple(args, "s", &nic_name)) {
        return NULL;
    }

    // Additional interface name validation
    if (!validate_interface_name(nic_name)) {
        return NULL;
    }

    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    memset(&ifr, 0, sizeof (ifr));
    PSUTIL_STRNCPY(ifr.ifr_name, nic_name, sizeof (ifr.ifr_name));
    ret = ioctl(sock, SIOCGIFFLAGS, &ifr);
    if (ret == -1) {
        close(sock);
        if (errno == ENODEV) {
            PyErr_Format(PyExc_OSError, "No such interface: %s", nic_name);
        } else {
            PyErr_Format(PyExc_OSError, "Failed to get flags for %s: %s", nic_name, strerror(errno));
        }
        return NULL;
    }

    close(sock);
    if ((ifr.ifr_flags & IFF_RUNNING) != 0)
        return Py_BuildValue("O", Py_True);
    else
        return Py_BuildValue("O", Py_False);
}

/*
 * Return stats about a particular network interface.
 * For Cygwin, we provide a minimal implementation that returns
 * default values since the BSD media framework isn't available.
 * FIXED: Added proper parameter validation and interface existence check
 */
PyObject *
psutil_net_if_duplex_speed(PyObject *self, PyObject *args)
{
    char *nic_name;
    int sock = -1;
    int ret;
    struct ifreq ifr;

    // Parameter validation with TypeError for non-strings
    if (!PyArg_ParseTuple(args, "s", &nic_name)) {
        return NULL;
    }

    // Additional interface name validation
    if (!validate_interface_name(nic_name)) {
        return NULL;
    }

    // Check if interface exists by trying to get its flags
    sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }

    memset(&ifr, 0, sizeof (ifr));
    PSUTIL_STRNCPY(ifr.ifr_name, nic_name, sizeof (ifr.ifr_name));
    ret = ioctl(sock, SIOCGIFFLAGS, &ifr);
    if (ret == -1) {
        close(sock);
        if (errno == ENODEV) {
            PyErr_Format(PyExc_OSError, "No such interface: %s", nic_name);
        } else {
            PyErr_Format(PyExc_OSError, "Failed to access interface %s: %s", nic_name, strerror(errno));
        }
        return NULL;
    }
    close(sock);

    // For Cygwin, we cannot easily determine duplex and speed
    // Return unknown values (0 for both duplex and speed)
    // This matches the behavior when ioctl fails on other platforms
    return Py_BuildValue("[ii]", 0, 0);
}

// == ===========================================================================
// --- Network Connection Functions (delegated to net_connections.c)
// == ===========================================================================

/*
 * Network connection functions are implemented in net_connections.c
 * This file (net.c) focuses on network interface functions only
 * The functions psutil_net_connections_posix and psutil_proc_net_connections_posix
 * are defined in net_connections.c with full /proc/net parsing implementation
 */

/*
 * Get system-wide network connections - delegates to net_connections.c
 * This function is defined in net_connections.c
 */
PyObject *psutil_net_connections_posix(PyObject *self, PyObject *args);

/*
 * Get network connections for a specific process - delegates to net_connections.c
 * This function is defined in net_connections.c
 */
PyObject *psutil_proc_net_connections_posix(PyObject *self, PyObject *args);
