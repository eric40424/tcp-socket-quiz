/*
 * P1: Iterative TCP echo server  —— 參考解答
 *
 * 用法: ./server <port>
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <unistd.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

#define BUF_SIZE 4096
#define BACKLOG 16

/* 把 len 個 bytes 全部送出去。成功回傳 0，失敗回傳 -1。 */
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

/* 服務一個 client：收到什麼就回什麼，直到對方關閉連線。 */
static void handle_client(int client_fd)
{
    char buf[BUF_SIZE];

    for (;;) {
        ssize_t n = recv(client_fd, buf, sizeof(buf), 0);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            perror("recv");
            break;
        }
        if (n == 0) /* [BUG 修正] 對方關閉連線 (收到 FIN) */
            break;
        if (send_all(client_fd, buf, (size_t)n) < 0) {
            perror("send");
            break;
        }
    }
    close(client_fd);
}

int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stderr, "usage: %s <port>\n", argv[0]);
        return 1;
    }
    int port = atoi(argv[1]);
    if (port <= 0 || port > 65535) {
        fprintf(stderr, "invalid port: %s\n", argv[1]);
        return 1;
    }

    /* 對已關閉的連線 send() 會觸發 SIGPIPE，預設行為是直接殺掉 process */
    signal(SIGPIPE, SIG_IGN);

    /* TODO 1-A */
    int listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) {
        perror("socket");
        return 1;
    }

    /* TODO 1-B */
    int opt = 1;
    if (setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
        perror("setsockopt");
        return 1;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons((uint16_t)port); /* [BUG 修正] 要轉成 network byte order */

    /* TODO 1-C */
    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(listen_fd);
        return 1;
    }
    if (listen(listen_fd, BACKLOG) < 0) {
        perror("listen");
        close(listen_fd);
        return 1;
    }

    printf("echo server listening on port %d\n", port);
    fflush(stdout);

    for (;;) {
        struct sockaddr_in cli;
        socklen_t cli_len = sizeof(cli);

        /* TODO 1-D */
        int client_fd = accept(listen_fd, (struct sockaddr *)&cli, &cli_len);
        if (client_fd < 0) {
            if (errno == EINTR)
                continue;
            perror("accept");
            continue;
        }

        char ip[INET_ADDRSTRLEN];
        inet_ntop(AF_INET, &cli.sin_addr, ip, sizeof(ip));
        printf("client %s:%d connected\n", ip, ntohs(cli.sin_port));
        fflush(stdout);

        handle_client(client_fd);

        printf("client %s:%d disconnected\n", ip, ntohs(cli.sin_port));
        fflush(stdout);
    }

    close(listen_fd);
    return 0;
}
