/*
 * Copyright (c) 2009, Giampaolo Rodola'. All rights reserved.
 * Use of this source code is governed by a BSD-style license that can be
 * found in the LICENSE file.
 *
 * Win32 API functions for Cygwin - cherry-picked from arch/windows/
 * These functions call Windows APIs directly via Cygwin's w32api layer.
 * No WinSock headers — only kernel32, powrprof, psapi, tlhelp32.
 */

#include <Python.h>
#include <windows.h>
#include <tlhelp32.h>
#include <sys/cygwin.h>

/*
 * Cygwin does not ship PowrProf.h with the PROCESSOR_POWER_INFORMATION
 * struct, and the w32api header may be incomplete.  Define what we need
 * locally so the build never depends on SDK version.
 */
typedef struct _PROCESSOR_POWER_INFORMATION {
    ULONG Number;
    ULONG MaxMhz;
    ULONG CurrentMhz;
    ULONG MhzLimit;
    ULONG MaxIdleState;
    ULONG CurrentIdleState;
} PROCESSOR_POWER_INFORMATION;

/* CallNtPowerInformation lives in powrprof.dll */
typedef LONG (WINAPI *CallNtPowerInformation_t)(
    int InformationLevel,
    PVOID InputBuffer,
    ULONG InputBufferLength,
    PVOID OutputBuffer,
    ULONG OutputBufferLength
);

/* ProcessorInformation = 11 */
#ifndef ProcessorInformation
#define ProcessorInformation 11
#endif

#include "init.h"

/*
 * Cygwin Python doesn't have PyErr_SetFromWindowsErr.
 * Map GetLastError() to a Python OSError with the Windows error code.
 */
static void
psutil_PyErr_SetFromWindowsErr(DWORD err)
{
    if (err == 0)
        err = GetLastError();
    PyErr_Format(PyExc_OSError, "Windows error %lu", (unsigned long)err);
}

/* ===================================================================
 * --- cpu_freq (from arch/windows/cpu.c)
 * =================================================================== */

/*
 * Return CPU frequency as (current_mhz, max_mhz).
 * Uses CallNtPowerInformation(ProcessorInformation) from powrprof.dll.
 */
PyObject *
psutil_cpu_freq_win32(PyObject *self, PyObject *args)
{
    HMODULE hMod;
    CallNtPowerInformation_t pCallNtPowerInformation;
    PROCESSOR_POWER_INFORMATION *ppi;
    ULONG ncpus;
    ULONG size;
    LPBYTE pBuffer = NULL;
    LONG ret;
    SYSTEM_INFO si;

    /* Get CPU count */
    GetSystemInfo(&si);
    ncpus = si.dwNumberOfProcessors;
    if (ncpus == 0) {
        PyErr_SetString(PyExc_RuntimeError, "GetSystemInfo returned 0 CPUs");
        return NULL;
    }

    /* Load powrprof.dll dynamically to avoid link-time dependency issues */
    hMod = LoadLibraryA("powrprof.dll");
    if (hMod == NULL) {
        PyErr_SetString(PyExc_RuntimeError,
                        "could not load powrprof.dll");
        return NULL;
    }

    pCallNtPowerInformation = (CallNtPowerInformation_t)
        GetProcAddress(hMod, "CallNtPowerInformation");
    if (pCallNtPowerInformation == NULL) {
        FreeLibrary(hMod);
        PyErr_SetString(PyExc_RuntimeError,
                        "could not find CallNtPowerInformation in powrprof.dll");
        return NULL;
    }

    /* Allocate buffer */
    size = ncpus * sizeof(PROCESSOR_POWER_INFORMATION);
    pBuffer = (BYTE *)malloc(size);
    if (pBuffer == NULL) {
        FreeLibrary(hMod);
        PyErr_NoMemory();
        return NULL;
    }

    /* Query */
    ret = pCallNtPowerInformation(ProcessorInformation, NULL, 0, pBuffer, size);
    if (ret != 0) {
        free(pBuffer);
        FreeLibrary(hMod);
        PyErr_Format(PyExc_RuntimeError,
                     "CallNtPowerInformation failed with status %ld", ret);
        return NULL;
    }

    ppi = (PROCESSOR_POWER_INFORMATION *)pBuffer;
    /* Return first CPU's values — Windows doesn't support per-cpu freq */
    PyObject *result = Py_BuildValue("kk",
                                     (unsigned long)ppi->CurrentMhz,
                                     (unsigned long)ppi->MaxMhz);
    free(pBuffer);
    FreeLibrary(hMod);
    return result;
}

/* ===================================================================
 * --- sensors_battery (from arch/windows/sensors.c)
 * =================================================================== */

/*
 * Return battery information as (acline_status, flags, percent, secsleft).
 * Uses GetSystemPowerStatus() from kernel32.
 */
PyObject *
psutil_sensors_battery_win32(PyObject *self, PyObject *args)
{
    SYSTEM_POWER_STATUS sps;

    if (GetSystemPowerStatus(&sps) == 0) {
        psutil_PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    return Py_BuildValue(
        "iiiI",
        sps.ACLineStatus,
        sps.BatteryFlag,
        sps.BatteryLifePercent,
        sps.BatteryLifeTime
    );
}

/* ===================================================================
 * --- proc_threads (from arch/windows/proc.c)
 * =================================================================== */

/*
 * Return list of (thread_id, user_time, system_time) for a process.
 * Uses CreateToolhelp32Snapshot + Thread32First/Next + GetThreadTimes.
 * PID is a Cygwin PID — converted to Windows PID internally.
 */
PyObject *
psutil_proc_threads_win32(PyObject *self, PyObject *args)
{
    pid_t cygpid;
    DWORD winpid;
    HANDLE hThreadSnap = INVALID_HANDLE_VALUE;
    HANDLE hThread = NULL;
    THREADENTRY32 te32;
    FILETIME ftDummy, ftKernel, ftUser;
    PyObject *py_tuple = NULL;
    PyObject *py_retlist = PyList_New(0);

    if (py_retlist == NULL)
        return NULL;
    if (!PyArg_ParseTuple(args, "i", &cygpid))
        goto error;

    /* Convert Cygwin PID to Windows PID */
    winpid = (DWORD)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, cygpid);
    if (winpid == 0) {
        /* PID conversion failed — process may not exist or may be
         * a pure-Cygwin process without a Windows counterpart.
         * Fall back: return empty list so Python layer can handle it. */
        return py_retlist;
    }

    hThreadSnap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (hThreadSnap == INVALID_HANDLE_VALUE) {
        psutil_PyErr_SetFromWindowsErr(0);
        goto error;
    }

    te32.dwSize = sizeof(THREADENTRY32);
    if (!Thread32First(hThreadSnap, &te32)) {
        psutil_PyErr_SetFromWindowsErr(0);
        goto error;
    }

    /* HI_T / LO_T from upstream: converts FILETIME to seconds */
#define HI_T 429.4967296
#define LO_T 0.0000001

    do {
        if (te32.th32OwnerProcessID == winpid) {
            hThread = OpenThread(THREAD_QUERY_INFORMATION,
                                 FALSE, te32.th32ThreadID);
            if (hThread == NULL)
                continue;  /* thread vanished */

            if (GetThreadTimes(hThread, &ftDummy, &ftDummy,
                               &ftKernel, &ftUser) == 0) {
                CloseHandle(hThread);
                continue;  /* can't read times — skip */
            }

            py_tuple = Py_BuildValue(
                "kdd",
                (unsigned long)te32.th32ThreadID,
                (double)(ftUser.dwHighDateTime * HI_T +
                         ftUser.dwLowDateTime * LO_T),
                (double)(ftKernel.dwHighDateTime * HI_T +
                         ftKernel.dwLowDateTime * LO_T));

            CloseHandle(hThread);
            hThread = NULL;

            if (!py_tuple)
                goto error;
            if (PyList_Append(py_retlist, py_tuple))
                goto error;
            Py_CLEAR(py_tuple);
        }
    } while (Thread32Next(hThreadSnap, &te32));

#undef HI_T
#undef LO_T

    CloseHandle(hThreadSnap);
    return py_retlist;

error:
    Py_XDECREF(py_tuple);
    Py_DECREF(py_retlist);
    if (hThread != NULL)
        CloseHandle(hThread);
    if (hThreadSnap != INVALID_HANDLE_VALUE)
        CloseHandle(hThreadSnap);
    return NULL;
}

/* ===================================================================
 * --- cpu_affinity (from arch/windows/proc.c concept)
 * =================================================================== */

/*
 * Return list of CPU indices this process is allowed to run on.
 * Uses GetProcessAffinityMask from kernel32.
 */
PyObject *
psutil_proc_cpu_affinity_get_win32(PyObject *self, PyObject *args)
{
    pid_t cygpid;
    DWORD winpid;
    HANDLE hProcess;
    DWORD_PTR proc_mask, sys_mask;
    PyObject *py_list;
    int i;

    if (!PyArg_ParseTuple(args, "i", &cygpid))
        return NULL;

    winpid = (DWORD)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, cygpid);
    if (winpid == 0) {
        PyErr_Format(PyExc_ProcessLookupError,
                     "process %d not found", cygpid);
        return NULL;
    }

    hProcess = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, winpid);
    if (hProcess == NULL) {
        psutil_PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    if (!GetProcessAffinityMask(hProcess, &proc_mask, &sys_mask)) {
        psutil_PyErr_SetFromWindowsErr(0);
        CloseHandle(hProcess);
        return NULL;
    }
    CloseHandle(hProcess);

    py_list = PyList_New(0);
    if (py_list == NULL)
        return NULL;

    for (i = 0; i < (int)(sizeof(DWORD_PTR) * 8); i++) {
        if (proc_mask & ((DWORD_PTR)1 << i)) {
            PyObject *py_cpu = PyLong_FromLong(i);
            if (py_cpu == NULL) {
                Py_DECREF(py_list);
                return NULL;
            }
            if (PyList_Append(py_list, py_cpu)) {
                Py_DECREF(py_cpu);
                Py_DECREF(py_list);
                return NULL;
            }
            Py_DECREF(py_cpu);
        }
    }
    return py_list;
}

/*
 * Set CPU affinity for a process.
 * Takes a list of CPU indices, converts to a bitmask.
 */
PyObject *
psutil_proc_cpu_affinity_set_win32(PyObject *self, PyObject *args)
{
    pid_t cygpid;
    DWORD winpid;
    HANDLE hProcess;
    PyObject *py_cpus;
    DWORD_PTR mask = 0;
    Py_ssize_t i, len;

    if (!PyArg_ParseTuple(args, "iO", &cygpid, &py_cpus))
        return NULL;

    if (!PyList_Check(py_cpus) && !PyTuple_Check(py_cpus)) {
        PyErr_SetString(PyExc_TypeError, "cpus must be a list or tuple");
        return NULL;
    }

    len = PySequence_Size(py_cpus);
    if (len == 0) {
        PyErr_SetString(PyExc_ValueError, "cpus list must not be empty");
        return NULL;
    }

    for (i = 0; i < len; i++) {
        PyObject *item = PySequence_GetItem(py_cpus, i);
        long cpu = PyLong_AsLong(item);
        Py_DECREF(item);
        if (cpu == -1 && PyErr_Occurred())
            return NULL;
        if (cpu < 0 || cpu >= (long)(sizeof(DWORD_PTR) * 8)) {
            PyErr_Format(PyExc_ValueError, "invalid CPU index %ld", cpu);
            return NULL;
        }
        mask |= ((DWORD_PTR)1 << cpu);
    }

    winpid = (DWORD)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, cygpid);
    if (winpid == 0) {
        PyErr_Format(PyExc_ProcessLookupError,
                     "process %d not found", cygpid);
        return NULL;
    }

    hProcess = OpenProcess(PROCESS_SET_INFORMATION, FALSE, winpid);
    if (hProcess == NULL) {
        psutil_PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    if (!SetProcessAffinityMask(hProcess, mask)) {
        psutil_PyErr_SetFromWindowsErr(0);
        CloseHandle(hProcess);
        return NULL;
    }

    CloseHandle(hProcess);
    Py_RETURN_NONE;
}

/* ===================================================================
 * --- ionice (I/O priority via NtQueryInformationProcess)
 * =================================================================== */

typedef LONG (WINAPI *NtQueryInformationProcess_t)(
    HANDLE ProcessHandle,
    ULONG ProcessInformationClass,
    PVOID ProcessInformation,
    ULONG ProcessInformationLength,
    PULONG ReturnLength
);

#ifndef ProcessIoPriority
#define ProcessIoPriority 33
#endif

/*
 * Return I/O priority for a process (0-4).
 * Uses NtQueryInformationProcess from ntdll.dll.
 */
PyObject *
psutil_proc_ionice_get_win32(PyObject *self, PyObject *args)
{
    pid_t cygpid;
    DWORD winpid;
    HANDLE hProcess;
    ULONG io_priority = 0;
    LONG status;
    NtQueryInformationProcess_t pNtQuery;
    HMODULE hNtdll;

    if (!PyArg_ParseTuple(args, "i", &cygpid))
        return NULL;

    winpid = (DWORD)cygwin_internal(CW_CYGWIN_PID_TO_WINPID, cygpid);
    if (winpid == 0) {
        PyErr_Format(PyExc_ProcessLookupError,
                     "process %d not found", cygpid);
        return NULL;
    }

    hNtdll = GetModuleHandleA("ntdll.dll");
    if (hNtdll == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "could not get ntdll.dll handle");
        return NULL;
    }

    pNtQuery = (NtQueryInformationProcess_t)
        GetProcAddress(hNtdll, "NtQueryInformationProcess");
    if (pNtQuery == NULL) {
        PyErr_SetString(PyExc_RuntimeError,
                        "NtQueryInformationProcess not found in ntdll.dll");
        return NULL;
    }

    hProcess = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, winpid);
    if (hProcess == NULL) {
        psutil_PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    status = pNtQuery(hProcess, ProcessIoPriority,
                      &io_priority, sizeof(io_priority), NULL);
    CloseHandle(hProcess);

    if (status != 0) {
        PyErr_Format(PyExc_OSError,
                     "NtQueryInformationProcess(ProcessIoPriority) "
                     "failed with status 0x%lx", (unsigned long)status);
        return NULL;
    }

    return PyLong_FromUnsignedLong(io_priority);
}
