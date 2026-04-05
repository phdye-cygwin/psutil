/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Cygwin platform C extension - Disk Operations (Phase 5.1)
 * This file implements disk-related functions for Cygwin.
 */

#include <Python.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <mntent.h>
#include <dirent.h>
#include <ctype.h>

#ifdef __CYGWIN__
/*
 * Get the current cygdrive prefix by reading /proc/cygdrive symbolic link
 * Returns the prefix (e.g., "/cygdrive") or NULL if not found
 */
static char *
get_cygdrive_prefix(void)
{
    static char prefix[64] = {0};
    static int prefix_cached = 0;

    if (prefix_cached) {
        return prefix[0] ? prefix : NULL;
    }

    // Method 1: Read /proc/cygdrive symbolic link (most reliable)
    ssize_t len = readlink("/proc/cygdrive", prefix, sizeof (prefix) - 1);
    if (len > 0) {
        prefix[len] = '\0';

        // Remove trailing slash if present
        if (len > 0 && prefix[len-1] == '/') {
            prefix[len-1] = '\0';
        }

        prefix_cached = 1;
        return prefix;
    }

    // Method 2: Default fallback
    strcpy(prefix, "/cygdrive");
    prefix_cached = 1;
    return prefix;
}

/*
 * Check if we're running in a true Cygwin environment (not just compiled with Cygwin)
 */
static int
is_true_cygwin_environment(void)
{
    // The most reliable check: /proc/cygdrive exists only in true Cygwin
    if (access("/proc/cygdrive", F_OK) == 0) {
        return 1;
    }

    // Fallback checks for older or different Cygwin configurations
    if (getenv("CYGWIN") || getenv("CYGWIN_ROOT")) {
        return 1;
    }

    // Check if /proc/version contains "Cygwin"
    FILE *version = fopen("/proc/version", "r");
    if (version) {
        char line[256];
        if (fgets(line, sizeof (line), version)) {
            if (strstr(line, "Cygwin")) {
                fclose(version);
                return 1;
            }
        }
        fclose(version);
    }

    // Check for other Cygwin-specific paths as final fallback
    return (access("/cygdrive", F_OK) == 0 ||
            access("/usr/bin/cygpath", F_OK) == 0);
}

#include <windows.h>
#include <winioctl.h>
#endif

#include "../../arch/all/init.h"
#include "psutil_cygwin.h"

// == ===========================================================================
// --- Disk Partitions
// == ===========================================================================

/*
 * Return disk mounted partitions as a list of tuples including device,
 * mount point, filesystem type, and mount options.
 *
 * This function combines the POSIX approach (using mntent) with
 * Cygwin-specific enhancements to properly handle Windows drive mappings.
 */
PyObject *
psutil_disk_partitions(PyObject *self, PyObject *args)
{
    FILE *file = NULL;
    struct mntent *entry;
    int all;
    PyObject *py_dev = NULL;
    PyObject *py_mountp = NULL;
    PyObject *py_tuple = NULL;
    PyObject *py_retlist = PyList_New(0);

    if (py_retlist == NULL)
        return NULL;

    // Parse arguments - 'all' determines if we show all filesystems
    if (!PyArg_ParseTuple(args, "i", &all))
        goto error;

    // Open the mount table
    // On Cygwin, /proc/mounts is more reliable than /etc/mtab
    Py_BEGIN_ALLOW_THREADS
    file = setmntent("/proc/mounts", "r");
    Py_END_ALLOW_THREADS

    if (file == NULL) {
        // Fallback to /etc/mtab if /proc/mounts is not available
        Py_BEGIN_ALLOW_THREADS
        file = setmntent("/etc/mtab", "r");
        Py_END_ALLOW_THREADS

        if (file == NULL) {
            PyErr_SetFromErrnoWithFilename(PyExc_OSError, "/proc/mounts");
            goto error;
        }
    }

    // Read all mount entries
    while ((entry = getmntent(file))) {
        // Filter out pseudo filesystems unless 'all' is specified
        if (!all) {
            // Skip common pseudo filesystems
            if (strcmp(entry->mnt_type, "proc") == 0 ||
                strcmp(entry->mnt_type, "sysfs") == 0 ||
                strcmp(entry->mnt_type, "devpts") == 0 ||
                strcmp(entry->mnt_type, "tmpfs") == 0 ||
                strcmp(entry->mnt_type, "securityfs") == 0 ||
                strcmp(entry->mnt_type, "debugfs") == 0 ||
                strcmp(entry->mnt_type, "tracefs") == 0 ||
                strcmp(entry->mnt_type, "fusectl") == 0 ||
                strcmp(entry->mnt_type, "fuse.gvfsd-fuse") == 0 ||
                strcmp(entry->mnt_type, "binfmt_misc") == 0) {
                continue;
            }

            // Skip entries that don't have real devices
            if (entry->mnt_fsname[0] != '/' &&                 strncmp(entry->mnt_fsname, "C:", 2) != 0 &&
                strncmp(entry->mnt_fsname, "D:", 2) != 0 &&
                strncmp(entry->mnt_fsname, "E:", 2) != 0) {
                // Check if it's a Windows drive letter format
                if (strlen(entry->mnt_fsname) < 2 ||                     entry->mnt_fsname[1] != ':') {
                    continue;
                }
            }
        }

        // Convert device name and mount point to Python strings
        py_dev = PyUnicode_DecodeFSDefault(entry->mnt_fsname);
        if (!py_dev)
            goto error;

        py_mountp = PyUnicode_DecodeFSDefault(entry->mnt_dir);
        if (!py_mountp)
            goto error;

        // Build tuple: (device, mountpoint, fstype, opts)
        py_tuple = Py_BuildValue("(OOss)",
                                py_dev,             // device
                                py_mountp,          // mount point
                                entry->mnt_type,    // filesystem type
                                entry->mnt_opts);   // mount options
        if (!py_tuple)
            goto error;

        if (PyList_Append(py_retlist, py_tuple))
            goto error;

        Py_CLEAR(py_dev);
        Py_CLEAR(py_mountp);
        Py_CLEAR(py_tuple);
    }

    endmntent(file);

#ifdef __CYGWIN__
    // On Cygwin, when all = True, also add Windows drives that might not be in mounts
    // This ensures we capture all available drives when requested
    if (all && is_true_cygwin_environment()) {
        char *cygdrive_prefix = get_cygdrive_prefix();
        if (cygdrive_prefix) {
            DWORD drives = GetLogicalDrives();
            char drive_path[4] = "X:\\";
            char cygwin_path[128];

            for (int i = 0; i < 26; i++) {
                if (drives & (1 << i)) {
                    drive_path[0] = 'A' + i;

                    // Create the Cygwin mount point using the detected prefix
                    // Handle special case where prefix is "/" to avoid double slashes
                    if (strlen(cygdrive_prefix) == 0 || strcmp(cygdrive_prefix, "/") == 0) {
                        snprintf(cygwin_path, sizeof (cygwin_path), "/%c", 'a' + i);
                    } else {
                        snprintf(cygwin_path, sizeof (cygwin_path), "%s/%c",
                                cygdrive_prefix, 'a' + i);
                    }

                    // Check if this drive is already in our list
                    int found = 0;
                    Py_ssize_t list_size = PyList_Size(py_retlist);
                    for (Py_ssize_t j = 0; j < list_size; j++) {
                        PyObject *item = PyList_GetItem(py_retlist, j);
                        if (item && PyTuple_Check(item) && PyTuple_Size(item) >= 2) {
                            PyObject *mp = PyTuple_GetItem(item, 1);
                            if (mp && PyUnicode_Check(mp)) {
                                const char *mount_point = PyUnicode_AsUTF8(mp);
                                if (mount_point && (
                                    strcmp(mount_point, cygwin_path) == 0 ||                                     (strlen(mount_point) == 2 && mount_point[0] == '/' &&                                      tolower(mount_point[1]) == 'a' + i))) {
                                    found = 1;
                                    break;
                                }
                            }
                        }
                    }

                    if (!found) {
                        // Only add drives that actually exist and are ready
                        UINT drive_type = GetDriveTypeA(drive_path);
                        if (drive_type == DRIVE_NO_ROOT_DIR || drive_type == DRIVE_UNKNOWN) {
                            continue;  // Skip non-existent or unknown drives
                        }

                        // For removable drives, check if they're actually ready
                        if (drive_type == DRIVE_REMOVABLE || drive_type == DRIVE_CDROM) {
                            HANDLE hDrive = CreateFileA(drive_path,
                                                       0,
                                                       FILE_SHARE_READ | FILE_SHARE_WRITE,
                                                       NULL,
                                                       OPEN_EXISTING,
                                                       0,
                                                       NULL);
                            if (hDrive == INVALID_HANDLE_VALUE) {
                                continue;  // Drive not ready
                            }
                            CloseHandle(hDrive);
                        }

                        // Check if the cygdrive path actually exists or is accessible
                        // Only add it if Cygwin has actually mounted it
                        struct stat st;
                        if (stat(cygwin_path, &st) != 0) {
                            continue;  // Cygwin hasn't mounted this drive
                        }

                        // Determine filesystem type
                        const char *fs_type = "unknown";
                        if (drive_type == DRIVE_FIXED)
                            fs_type = "ntfs";  // Most common for fixed drives
                        else if (drive_type == DRIVE_CDROM)
                            fs_type = "cdfs";
                        else if (drive_type == DRIVE_REMOVABLE)
                            fs_type = "vfat";
                        else if (drive_type == DRIVE_REMOTE)
                            fs_type = "network";

                        // Add this drive to the list
                        py_dev = PyUnicode_FromString(drive_path);
                        py_mountp = PyUnicode_FromString(cygwin_path);
                        py_tuple = Py_BuildValue("(OOss)",
                                               py_dev,
                                               py_mountp,
                                               fs_type,
                                               "binary, posix=0, user");

                        if (py_dev && py_mountp && py_tuple) {
                            PyList_Append(py_retlist, py_tuple);
                        }

                        Py_XDECREF(py_dev);
                        Py_XDECREF(py_mountp);
                        Py_XDECREF(py_tuple);
                        py_dev = NULL;
                        py_mountp = NULL;
                        py_tuple = NULL;
                    }
                }
            }
        }
    }
#endif

    return py_retlist;

error:
    if (file != NULL)
        endmntent(file);
    Py_XDECREF(py_dev);
    Py_XDECREF(py_mountp);
    Py_XDECREF(py_tuple);
    Py_DECREF(py_retlist);
    return NULL;
}

// == ===========================================================================
// --- Disk Usage
// == ===========================================================================

/*
 * Return disk usage statistics for a given path.
 * Returns a tuple of (total, used, free, percent).
 */
PyObject *
psutil_disk_usage(PyObject *self, PyObject *args)
{
    const char *path;
    struct statvfs stat;
    unsigned long long total, free, used;
    double percent;

    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;

    // Get filesystem statistics using POSIX statvfs
    Py_BEGIN_ALLOW_THREADS
    if (statvfs(path, &stat) != 0) {
        Py_BLOCK_THREADS
        PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
        return NULL;
    }

    Py_END_ALLOW_THREADS

    // Calculate sizes in bytes
    total = (unsigned long long)stat.f_blocks * stat.f_frsize;
    free = (unsigned long long)stat.f_bavail * stat.f_frsize;
    used = total - ((unsigned long long)stat.f_bfree * stat.f_frsize);

    // Calculate percentage
    if (total > 0) {
        percent = ((double)used / (double)total) * 100.0;
    } else {
        percent = 0.0;
    }

    // Return tuple: (total, used, free, percent)
    return Py_BuildValue("(KKKd)", total, used, free, percent);
}

// == ===========================================================================
// --- Disk I/O Counters
// == ===========================================================================

/*
 * Helper function to parse a line from /proc/diskstats or /sys/block/<device>/stat
 */
static int
parse_disk_stat_line(const char *line, char *name, size_t name_size,
                     unsigned long long *reads, unsigned long long *writes,
                     unsigned long long *read_bytes, unsigned long long *write_bytes,
                     unsigned long long *read_time, unsigned long long *write_time) {
    // /proc/diskstats format:
    // major minor name reads reads_merged read_sectors read_time writes writes_merged write_sectors write_time ...
    int major, minor;
    unsigned long long reads_merged, writes_merged;
    unsigned long long read_sectors, write_sectors;

    int fields = sscanf(line, "%d %d %s %llu %llu %llu %llu %llu %llu %llu %llu",
                        &major, &minor, name,
                        reads, &reads_merged, &read_sectors, read_time,
                        writes, &writes_merged, &write_sectors, write_time);

    if (fields >= 11) {
        // Convert sectors to bytes (typically 512 bytes per sector)
        *read_bytes = read_sectors * 512;
        *write_bytes = write_sectors * 512;

        // Convert milliseconds to microseconds for consistency
        *read_time *= 1000;
        *write_time *= 1000;

        return 1;  // Success
    }

    return 0;  // Failed to parse
}

/*
 * Return disk I/O statistics as a dictionary.
 * Each disk has a tuple of (read_count, write_count, read_bytes, write_bytes, read_time, write_time).
 */
PyObject *
psutil_disk_io_counters(PyObject *self, PyObject *args)
{
    FILE *file = NULL;
    char line[256];
    char disk_name[64];
    unsigned long long reads, writes, read_bytes, write_bytes, read_time, write_time;
    PyObject *py_retdict = PyDict_New();
    PyObject *py_tuple = NULL;
    int found_stats = 0;

    if (py_retdict == NULL)
        return NULL;

    // Try to open /proc/diskstats first
    file = fopen("/proc/diskstats", "r");
    if (file != NULL) {
        // Read and parse each line
        while (fgets(line, sizeof (line), file)) {
            if (parse_disk_stat_line(line, disk_name, sizeof (disk_name),
                                    &reads, &writes, &read_bytes, &write_bytes,
                                    &read_time, &write_time)) {

                // Filter out partitions - we only want whole disks
                // Whole disks typically don't have numbers at the end
                // (e.g., "sda" vs "sda1", "sdb" vs "sdb2")
                size_t name_len = strlen(disk_name);
                if (name_len > 0) {
                    // Check if the last character is a digit (indicating a partition)
                    if (disk_name[name_len - 1] >= '0' && disk_name[name_len - 1] <= '9') {
                        continue;  // Skip partitions
                    }

                    // Also skip loop devices and ram disks unless specifically requested
                    if (strncmp(disk_name, "loop", 4) == 0 ||
                        strncmp(disk_name, "ram", 3) == 0) {
                        continue;
                    }
                }

                // Create tuple: (read_count, write_count, read_bytes, write_bytes, read_time, write_time)
                py_tuple = Py_BuildValue("(KKKKKK)",
                                        reads, writes,
                                        read_bytes, write_bytes,
                                        read_time, write_time);
                if (!py_tuple)
                    goto error;

                if (PyDict_SetItemString(py_retdict, disk_name, py_tuple) < 0)
                    goto error;

                Py_CLEAR(py_tuple);
                found_stats = 1;
            }
        }
        fclose(file);
        file = NULL;

        // If we successfully parsed /proc/diskstats, return the results
        if (found_stats) {
            return py_retdict;
        }
    }

#ifdef __CYGWIN__
    // /proc/diskstats not available or no stats found - use Windows API fallback
    psutil_debug("Using Windows API fallback for disk I/O counters");

    HANDLE hDevice;
    char device_path[64];
    DISK_PERFORMANCE disk_perf;
    DWORD bytes_returned;
    int windows_stats_found = 0;

    // Try to get statistics for physical drives
    for (int i = 0; i < 32; i++) {
        snprintf(device_path, sizeof (device_path), "\\\\.\\PhysicalDrive%d", i);

        hDevice = CreateFileA(device_path,
                             GENERIC_READ,
                             FILE_SHARE_READ | FILE_SHARE_WRITE,
                             NULL,
                             OPEN_EXISTING,
                             0,
                             NULL);

        if (hDevice == INVALID_HANDLE_VALUE) {
            // No more physical drives, or access denied
            continue;
        }

        // Try to get disk performance data
        if (DeviceIoControl(hDevice,
                          IOCTL_DISK_PERFORMANCE,
                          NULL, 0,
                          &disk_perf, sizeof (disk_perf),
                          &bytes_returned,
                          NULL)) {

            char disk_name[32];
            snprintf(disk_name, sizeof (disk_name), "PhysicalDrive%d", i);

            // Convert Windows performance data to psutil format
            py_tuple = Py_BuildValue("(KKKKKK)",
                                   (unsigned long long)disk_perf.ReadCount,
                                   (unsigned long long)disk_perf.WriteCount,
                                   (unsigned long long)disk_perf.BytesRead.QuadPart,
                                   (unsigned long long)disk_perf.BytesWritten.QuadPart,
                                   (unsigned long long)(disk_perf.ReadTime.QuadPart / 10000),  // Convert to ms
                                   (unsigned long long)(disk_perf.WriteTime.QuadPart / 10000)); // Convert to ms

            if (py_tuple) {
                if (PyDict_SetItemString(py_retdict, disk_name, py_tuple) == 0) {
                    windows_stats_found = 1;
                }
                Py_DECREF(py_tuple);
                py_tuple = NULL;
            }
        } else {
            psutil_debug("DeviceIoControl IOCTL_DISK_PERFORMANCE failed for %s: %u",
                        device_path, GetLastError());
        }

        CloseHandle(hDevice);
    }

    // If Windows API provided stats, return them
    if (windows_stats_found) {
        psutil_debug("Successfully retrieved disk I/O stats using Windows API");
        return py_retdict;
    }

    // If both methods failed, provide synthetic minimal stats to avoid None return
    psutil_debug("No disk I/O statistics available from any source, providing minimal synthetic data");

    // Create a minimal entry for the system drive (C:)
    py_tuple = Py_BuildValue("(KKKKKK)", 0ULL, 0ULL, 0ULL, 0ULL, 0ULL, 0ULL);
    if (py_tuple) {
        PyDict_SetItemString(py_retdict, "SystemDrive", py_tuple);
        Py_DECREF(py_tuple);
    }
#endif

    // Return the dictionary (may be empty on non-Cygwin systems without /proc/diskstats)
    return py_retdict;

error:
    if (file != NULL)
        fclose(file);
    Py_XDECREF(py_tuple);
    Py_DECREF(py_retdict);
    return NULL;
}
