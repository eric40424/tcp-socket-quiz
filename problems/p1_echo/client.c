/*
 * P1: TCP echo client
 *
 * 用法: ./client <ipv4-address> <port>
 * 從 stdin 一行一行讀入，送給 server，再把 server 回傳的內容「完整地」印到 stdout。
 * stdout 只能印出 server 回傳的資料；錯誤訊息請印到 stderr。
 *
 * 請完成 TODO 1-F、1-G。
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

    /* TODO 1-F: 建立 TCP socket、填好 server 位址 (提示: inet_pton, htons)、connect() */
    int fd = -1;
    (void)host;
    (void)port;

    char line[BUF_SIZE];
    char buf[BUF_SIZE];

    while (fgets(line, sizeof(line), stdin) != NULL) {
        size_t len = strlen(line);
        if (send_all(fd, line, len) < 0) {
            perror("send");
            break;
        }

        /* TODO 1-G: 下面這段在本機手動測試時「看起來」沒問題，但其實是錯的。請改寫。 */
        ssize_t n = recv(fd, buf, sizeof(buf), 0);
        if (n <= 0)
            break;
        fwrite(buf, 1, (size_t)n, stdout);
        fflush(stdout);
    }

    close(fd);
    return 0;
}
