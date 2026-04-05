/*
 * Wrapper for psutil/_psutil_posix.c
 * This wrapper provides POSIX compatibility definitions for Cygwin
 * while keeping them isolated from Cygwin-specific code.
 */

/* Include our single POSIX compatibility header */
#include "../posix_compat.h"

/* Now include the actual POSIX source file */
#include "../../../_psutil_posix.c"
