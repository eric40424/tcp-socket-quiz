/*
 * P1: Iterative TCP echo server
 *
 * 用法: ./server <port>
 *
 * 規格:
 *   - 監聽 0.0.0.0:<port>
 *   - 一次服務一個 client：收到什麼就原封不動回傳，直到對方關閉連線
 *   - 一個 client 離開後，要能繼續服務下一個 client
 *   - server 被關掉後立刻重啟，必須能成功 bind 同一個 port
 *   - 成功 listen 之後要印出一行包含 "listening" 的訊息 (judge 用來判斷 server 已啟動)
 *
 * 請完成 TODO 1-A ~ 1-E。注意：這個檔案除了 TODO 之外還藏有 bug。
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
        /* TODO 1-E: 呼叫 send()。注意 send() 不保證一次送完，也可能被 signal 打斷 (EINTR) */
        ssize_t n = -1;

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

    /* TODO 1-A: 建立一個 IPv4 的 TCP socket */
    int listen_fd = -1;
    if (listen_fd < 0) {
        perror("socket");
        return 1;
    }

    /* TODO 1-B: 設定 SO_REUSEADDR，讓 server 重啟時不會因為 TIME_WAIT 而 bind 失敗 */

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = port;

    /* TODO 1-C: bind() 到 addr，然後 listen()，失敗時印出錯誤並結束程式 */

    printf("echo server listening on port %d\n", port);
    fflush(stdout);

    for (;;) {
        struct sockaddr_in cli;
        socklen_t cli_len = sizeof(cli);

        /* TODO 1-D: accept() 一個新連線，並取得對方的位址 (cli) */
        int client_fd = -1;
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
