/*
 * POSIX compatibility header for Cygwin
 * This provides minimal definitions needed for POSIX code compilation
 * without including system headers that cause conflicts
 */

#ifndef _POSIX_COMPAT_H
#define _POSIX_COMPAT_H 1

/* Standard includes needed by POSIX code */
#include <Python.h>
#include <sys/types.h>
#include <stdint.h>

/* Define missing types for POSIX code on Cygwin */
#ifndef __socklen_t_defined
typedef int socklen_t;
#define __socklen_t_defined
#endif

#ifndef __sa_family_t_defined
typedef unsigned short int sa_family_t;
#define __sa_family_t_defined
#endif

/* Network constants */
#ifndef NI_MAXHOST
#define NI_MAXHOST      1025
#endif

#ifndef NI_NUMERICHOST
#define NI_NUMERICHOST  1
#endif

#ifndef AF_INET
#define AF_INET         2
#endif

#ifndef AF_INET6
#define AF_INET6        23
#endif

/* Basic socket address structure for POSIX code */
#ifndef _SOCKADDR_DEFINED_FOR_POSIX
#define _SOCKADDR_DEFINED_FOR_POSIX
struct sockaddr {
    sa_family_t sa_family;
    char sa_data[14];
};
#endif

/* IPv4 address structure for POSIX code */
#ifndef _SOCKADDR_IN_DEFINED_FOR_POSIX
#define _SOCKADDR_IN_DEFINED_FOR_POSIX
typedef uint32_t in_addr_t;
typedef uint16_t in_port_t;

struct in_addr {
    in_addr_t s_addr;
};

struct sockaddr_in {
    sa_family_t sin_family;
    in_port_t sin_port;
    struct in_addr sin_addr;
    unsigned char sin_zero[8];
};
#endif

/* IPv6 address structure for POSIX code */
#ifndef _SOCKADDR_IN6_DEFINED_FOR_POSIX
#define _SOCKADDR_IN6_DEFINED_FOR_POSIX
struct in6_addr {
    union {
        uint8_t  __u6_addr8[16];
        uint16_t __u6_addr16[8];
        uint32_t __u6_addr32[4];
    } __in6_u;
};

struct sockaddr_in6 {
    sa_family_t sin6_family;
    in_port_t sin6_port;
    uint32_t sin6_flowinfo;
    struct in6_addr sin6_addr;
    uint32_t sin6_scope_id;
};
#endif

/* Function declarations for POSIX code */
#ifdef __cplusplus
extern "C" {
#endif

/* getnameinfo declaration for POSIX code */
extern int getnameinfo(const struct sockaddr *sa, socklen_t salen,
                      char *host, socklen_t hostlen,
                      char *serv, socklen_t servlen, int flags);

#ifdef __cplusplus
}
#endif

#endif /* _POSIX_COMPAT_H */
