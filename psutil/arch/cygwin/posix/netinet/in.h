/*
 * netinet/in.h - Internet address family for Cygwin compatibility
 * Based on POSIX.1-2008 and Linux implementations
 *
 * This file provides the missing network address structures and constants
 * required for POSIX network code compilation on Cygwin.
 */

#ifndef _NETINET_IN_H
#define _NETINET_IN_H 1

#include <sys/types.h>
#include <stdint.h>

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

/* Basic socket address structure - needed for sockaddr_in padding calculation */
/* Only define if not already defined by system headers */
#ifndef _STRUCT_SOCKADDR
#ifndef __sockaddr_defined
struct sockaddr {
    sa_family_t sa_family;      /* Address family */
    char sa_data[14];           /* Address data */
};
#define __sockaddr_defined
#endif
#endif

/* Standard well-defined IP protocols */
#define IPPROTO_IP      0       /* dummy for IP */
#define IPPROTO_ICMP    1       /* control message protocol */
#define IPPROTO_TCP     6       /* transmission control protocol */
#define IPPROTO_UDP     17      /* user datagram protocol */
#define IPPROTO_IPV6    41      /* IPv6 in IPv6 */
#define IPPROTO_ICMPV6  58      /* ICMPv6 */

/* Internet address families */
#ifndef AF_INET
#define AF_INET         2
#endif
#ifndef AF_INET6
#define AF_INET6        23
#endif
#define AF_UNSPEC       0

/* Protocol families */
#define PF_INET         AF_INET
#define PF_INET6        AF_INET6
#define PF_UNSPEC       AF_UNSPEC

/* Standard port definitions */
#define IPPORT_ECHO     7
#define IPPORT_DISCARD  9
#define IPPORT_SYSTAT   11
#define IPPORT_DAYTIME  13
#define IPPORT_NETSTAT  15
#define IPPORT_FTP      21
#define IPPORT_TELNET   23
#define IPPORT_SMTP     25
#define IPPORT_TIMESERVER 37
#define IPPORT_NAMESERVER 42
#define IPPORT_WHOIS    43
#define IPPORT_MTP      57
#define IPPORT_TFTP     69
#define IPPORT_RJE      77
#define IPPORT_FINGER   79
#define IPPORT_TTYLINK  87
#define IPPORT_SUPDUP   95
#define IPPORT_EXECSERVER 512
#define IPPORT_LOGINSERVER 513
#define IPPORT_CMDSERVER 514
#define IPPORT_EFSSERVER 520
#define IPPORT_BIFFUDP  512
#define IPPORT_WHOSERVER 513
#define IPPORT_ROUTESERVER 520
#define IPPORT_RESERVED 1024

/* Type definitions for network addresses */
typedef uint32_t in_addr_t;
typedef uint16_t in_port_t;

/* Special IPv4 addresses */
#define INADDR_ANY      ((in_addr_t) 0x00000000)
#define INADDR_BROADCAST ((in_addr_t) 0xffffffff)
#define INADDR_NONE     ((in_addr_t) 0xffffffff)
#define INADDR_LOOPBACK ((in_addr_t) 0x7f000001) /* 127.0.0.1 */

/* IPv4 address structure */
struct in_addr {
    in_addr_t s_addr;       /* IPv4 address */
};

/* IPv4 socket address structure */
struct sockaddr_in {
    sa_family_t     sin_family; /* AF_INET */
    in_port_t       sin_port;   /* port in network byte order */
    struct in_addr  sin_addr;   /* internet address */

    /* Pad to size of 'struct sockaddr' */
    unsigned char sin_zero[sizeof(struct sockaddr) -
                          sizeof(sa_family_t) -
                          sizeof(in_port_t) -
                          sizeof(struct in_addr)];
};

/* IPv6 address structure */
struct in6_addr {
    union {
        uint8_t  __u6_addr8[16];
        uint16_t __u6_addr16[8];
        uint32_t __u6_addr32[4];
    } __in6_u;
#define s6_addr                 __in6_u.__u6_addr8
#define s6_addr16               __in6_u.__u6_addr16
#define s6_addr32               __in6_u.__u6_addr32
};

/* IPv6 socket address structure */
struct sockaddr_in6 {
    sa_family_t     sin6_family;   /* AF_INET6 */
    in_port_t       sin6_port;     /* port number */
    uint32_t        sin6_flowinfo; /* IPv6 flow information */
    struct in6_addr sin6_addr;     /* IPv6 address */
    uint32_t        sin6_scope_id; /* Scope ID (new in 2.4) */
};

/* IPv6 multicast request structure */
struct ipv6_mreq {
    struct in6_addr ipv6mr_multiaddr; /* IPv6 multicast address */
    unsigned int    ipv6mr_interface; /* local interface */
};

/* Special IPv6 addresses */
extern const struct in6_addr in6addr_any;        /* :: */
extern const struct in6_addr in6addr_loopback;   /* ::1 */
#define IN6ADDR_ANY_INIT     { { { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 } } }
#define IN6ADDR_LOOPBACK_INIT { { { 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1 } } }

/* IPv6 address testing macros */
#define IN6_IS_ADDR_UNSPECIFIED(a) \
    (((const uint32_t *) (a))[0] == 0 && \
     ((const uint32_t *) (a))[1] == 0 && \
     ((const uint32_t *) (a))[2] == 0 && \
     ((const uint32_t *) (a))[3] == 0)

#define IN6_IS_ADDR_LOOPBACK(a) \
    (((const uint32_t *) (a))[0] == 0 && \
     ((const uint32_t *) (a))[1] == 0 && \
     ((const uint32_t *) (a))[2] == 0 && \
     ((const uint32_t *) (a))[3] == htonl(1))

#define IN6_IS_ADDR_MULTICAST(a) (((const uint8_t *) (a))[0] == 0xff)

#define IN6_IS_ADDR_LINKLOCAL(a) \
    ((((const uint32_t *) (a))[0] & htonl(0xffc00000)) == htonl(0xfe800000))

#define IN6_IS_ADDR_SITELOCAL(a) \
    ((((const uint32_t *) (a))[0] & htonl(0xffc00000)) == htonl(0xfec00000))

/* Function declarations */
#ifdef __cplusplus
extern "C" {
#endif

/* Network byte order conversion functions */
uint32_t htonl(uint32_t hostlong);
uint16_t htons(uint16_t hostshort);
uint32_t ntohl(uint32_t netlong);
uint16_t ntohs(uint16_t netshort);

/* IPv4/IPv6 address conversion functions */
int inet_aton(const char *cp, struct in_addr *inp);
in_addr_t inet_addr(const char *cp);
in_addr_t inet_network(const char *cp);
char *inet_ntoa(struct in_addr in);
struct in_addr inet_makeaddr(in_addr_t net, in_addr_t host);
in_addr_t inet_lnaof(struct in_addr in);
in_addr_t inet_netof(struct in_addr in);

/* Modern IPv4/IPv6 address conversion functions */
int inet_pton(int af, const char *src, void *dst);
const char *inet_ntop(int af, const void *src, char *dst, socklen_t size);

#ifdef __cplusplus
}
#endif

#endif /* _NETINET_IN_H */
