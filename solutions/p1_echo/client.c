/*
 * P1: TCP echo client  —— 參考解答
 *
 * 用法: ./client <ipv4-address> <port>
 * 從 stdin 一行一行讀入，送給 server，把 server 回傳的內容印到 stdout。
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define BUF_SIZE 4096

static int send_all(int fd, const char *buf, size_t len)
{
    size_t sent = 0;
    while (sent < len) {
        ssize_t n = send(fd, buf + sent, len - sent, 0);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        sent += (size_t)n;
    }
    return 0;
}

int main(int argc, char *argv[])
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s <ipv4-address> <port>\n", argv[0]);
        return 1;
    }
    const char *host = argv[1];
    int port = atoi(argv[2]);

    /* TODO 1-F */
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        perror("socket");
        return 1;
    }
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)port);
    if (inet_pton(AF_INET, host, &addr.sin_addr) != 1) {
        fprintf(stderr, "invalid address: %s\n", host);
        close(fd);
        return 1;
    }
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect");
        close(fd);
        return 1;
    }

    char line[BUF_SIZE];
    char buf[BUF_SIZE];

    while (fgets(line, sizeof(line), stdin) != NULL) {
        size_t len = strlen(line);
        if (send_all(fd, line, len) < 0) {
            perror("send");
            break;
        }

        /* TODO 1-G: TCP 是 byte stream，要一直 recv 到剛好收滿 len bytes */
        size_t got = 0;
        while (got < len) {
            ssize_t n = recv(fd, buf + got, len - got, 0);
            if (n < 0) {
                if (errno == EINTR)
                    continue;
                perror("recv");
                close(fd);
                return 1;
            }
            if (n == 0) {
                fprintf(stderr, "server closed the connection\n");
                close(fd);
                return 1;
            }
            got += (size_t)n;
        }
        fwrite(buf, 1, got, stdout);
        fflush(stdout);
    }

    close(fd);
    return 0;
}
