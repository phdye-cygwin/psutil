/*
 * netdb.h - Network database definitions for Cygwin compatibility
 * Based on POSIX.1-2008 and glibc specifications
 *
 * This file provides the missing network database constants and structures
 * required for POSIX network code compilation on Cygwin.
 */

#ifndef _NETDB_H
#define _NETDB_H 1

#include <sys/types.h>
#include <stdint.h>

/* Define socket types that may be missing in Cygwin */
#ifndef __socklen_t_defined
typedef unsigned int socklen_t;
#define __socklen_t_defined
#endif

#ifndef __sa_family_t_defined
typedef unsigned short int sa_family_t;
#define __sa_family_t_defined
#endif

/* Basic socket address structure */
#ifndef __sockaddr_defined
struct sockaddr {
    sa_family_t sa_family;      /* Address family */
    char sa_data[14];           /* Address data */
};
#define __sockaddr_defined
#endif

/* Include netinet/in.h after types are defined */
#include <netinet/in.h>

/* Error constants for network database functions */
#define NETDB_INTERNAL  -1  /* see errno */
#define NETDB_SUCCESS   0   /* no problem */
#define HOST_NOT_FOUND  1   /* Authoritative Answer Host not found */
#define TRY_AGAIN   2   /* Non-Authoritative Host not found, or SERVERFAIL */
#define NO_RECOVERY 3   /* Non recoverable errors, FORMERR, REFUSED, NOTIMP */
#define NO_DATA     4   /* Valid name, no data record of requested type */
#define NO_ADDRESS  NO_DATA /* no address, look for MX record */

/* Constants for getnameinfo() */
#define NI_MAXHOST  1025
#define NI_MAXSERV  32
#define NI_NUMERICHOST  1
#define NI_NUMERICSERV  2
#define NI_NOFQDN   4
#define NI_NAMEREQD 8
#define NI_DGRAM    16

/* Constants for getaddrinfo() */
#define AI_PASSIVE  1
#define AI_CANONNAME    2
#define AI_NUMERICHOST  4
#define AI_NUMERICSERV  1024
#define AI_ALL      256
#define AI_ADDRCONFIG   1024
#define AI_V4MAPPED 2048

/* Error values for getaddrinfo() */
#define EAI_BADFLAGS    -1
#define EAI_NONAME  -2
#define EAI_AGAIN   -3
#define EAI_FAIL    -4
#define EAI_FAMILY  -6
#define EAI_SOCKTYPE    -7
#define EAI_SERVICE -8
#define EAI_MEMORY  -10
#define EAI_SYSTEM  -11
#define EAI_OVERFLOW    -12

/* Address families */
#ifndef AF_INET
#define AF_INET     2
#endif
#ifndef AF_INET6
#define AF_INET6    23
#endif

/* Protocol families */
#define PF_INET     AF_INET
#define PF_INET6    AF_INET6
#define PF_UNSPEC   AF_UNSPEC

/* Standard port definitions */
#define IPPORT_RESERVED 1024

/* Host entry structure */
struct hostent {
    char    *h_name;        /* official name of host */
    char    **h_aliases;    /* alias list */
    int     h_addrtype;     /* host address type */
    int     h_length;       /* length of address */
    char    **h_addr_list;  /* list of addresses */
};
#define h_addr h_addr_list[0]   /* for backward compatibility */

/* Network entry structure */
struct netent {
    char     *n_name;       /* official name of net */
    char     **n_aliases;   /* alias list */
    int      n_addrtype;    /* net address type */
    uint32_t n_net;         /* network # */
};

/* Protocol entry structure */
struct protoent {
    char    *p_name;        /* official protocol name */
    char    **p_aliases;    /* alias list */
    int     p_proto;        /* protocol # */
};

/* Service entry structure */
struct servent {
    char    *s_name;        /* official service name */
    char    **s_aliases;    /* alias list */
    int     s_port;         /* port # */
    char    *s_proto;       /* protocol to use */
};

/* Address info structure for getaddrinfo() */
struct addrinfo {
    int              ai_flags;     /* AI_PASSIVE, AI_CANONNAME, AI_NUMERICHOST */
    int              ai_family;    /* PF_xxx */
    int              ai_socktype;  /* SOCK_xxx */
    int              ai_protocol;  /* 0 or IPPROTO_xxx for IPv4 and IPv6 */
    socklen_t        ai_addrlen;   /* length of ai_addr */
    char            *ai_canonname; /* canonical name for hostname */
    struct sockaddr *ai_addr;      /* binary address */
    struct addrinfo *ai_next;      /* next structure in linked list */
};

#ifdef __cplusplus
extern "C" {
#endif

/* Function declarations */
struct hostent *gethostbyname(const char *name);
struct hostent *gethostbyaddr(const void *addr, socklen_t len, int type);
struct hostent *gethostent(void);
void sethostent(int stayopen);
void endhostent(void);

struct netent *getnetbyname(const char *name);
struct netent *getnetbyaddr(uint32_t net, int type);
struct netent *getnetent(void);
void setnetent(int stayopen);
void endnetent(void);

struct protoent *getprotobyname(const char *name);
struct protoent *getprotobynumber(int proto);
struct protoent *getprotoent(void);
void setprotoent(int stayopen);
void endprotoent(void);

struct servent *getservbyname(const char *name, const char *proto);
struct servent *getservbyport(int port, const char *proto);
struct servent *getservent(void);
void setservent(int stayopen);
void endservent(void);

/* Modern name resolution functions */
int getaddrinfo(const char *node, const char *service,
                const struct addrinfo *hints,
                struct addrinfo **res);
void freeaddrinfo(struct addrinfo *res);
const char *gai_strerror(int errcode);

int getnameinfo(const struct sockaddr *sa, socklen_t salen,
                char *host, socklen_t hostlen,
                char *serv, socklen_t servlen, int flags);

/* Error handling */
extern int h_errno;
void herror(const char *s);
const char *hstrerror(int err);

#ifdef __cplusplus
}
#endif

#endif /* _NETDB_H */
