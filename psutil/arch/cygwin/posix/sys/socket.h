/*
 * sys/socket.h - Socket interface wrapper for Cygwin compatibility
 *
 * This wrapper ensures that network headers are automatically included
 * when POSIX code includes <sys/socket.h>, providing the missing
 * network constants and structures required for compilation.
 */

#ifndef _SYS_SOCKET_H
#define _SYS_SOCKET_H 1

/* Include the system sys/socket.h first */
#include_next <sys/socket.h>

/* Define socket types that may be missing in Cygwin */
#ifndef __socklen_t_defined
/* Cygwin defines socklen_t as int, not unsigned int */
typedef int socklen_t;
#define __socklen_t_defined
#endif

#ifndef __sa_family_t_defined
typedef unsigned short int sa_family_t;
#define __sa_family_t_defined
#endif

/* Socket types */
#ifndef SOCK_STREAM
#define SOCK_STREAM     1       /* stream socket */
#endif
#ifndef SOCK_DGRAM
#define SOCK_DGRAM      2       /* datagram socket */
#endif
#ifndef SOCK_RAW
#define SOCK_RAW        3       /* raw-protocol interface */
#endif

/* Address families */
#ifndef AF_UNSPEC
#define AF_UNSPEC       0       /* unspecified */
#endif
#ifndef AF_INET
#define AF_INET         2       /* internetwork: UDP, TCP, etc. */
#endif
#ifndef AF_INET6
#define AF_INET6        23      /* IPv6 */
#endif

/* Protocol families */
#ifndef PF_UNSPEC
#define PF_UNSPEC       AF_UNSPEC
#endif
#ifndef PF_INET
#define PF_INET         AF_INET
#endif
#ifndef PF_INET6
#define PF_INET6        AF_INET6
#endif

/* For Cygwin builds, include network headers after types are defined */
#ifdef PSUTIL_CYGWIN
    /* Include our complete internet address definitions */
    #include "netinet/in.h"
    /* Include our complete network database definitions */
    #include "netdb.h"
#endif

#endif /* _SYS_SOCKET_H */
