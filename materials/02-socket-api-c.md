# 02. Berkeley Socket API (C 語言)

> P1 的必備知識。所有函式都可以 `man 2 <函式名>` 查詢。

## 1. 整體流程

```
         Server                             Client
   ┌──────────────┐                   ┌──────────────┐
   │   socket()   │                   │   socket()   │
   └──────┬───────┘                   └──────┬───────┘
   ┌──────▼───────┐                          │
   │ setsockopt() │ SO_REUSEADDR             │
   └──────┬───────┘                          │
   ┌──────▼───────┐                          │
   │    bind()    │ 綁定 IP:port             │
   └──────┬───────┘                          │
   ┌──────▼───────┐                          │
   │   listen()   │ 開始接受連線             │
   └──────┬───────┘                          │
   ┌──────▼───────┐  3-way handshake  ┌──────▼───────┐
   │   accept()   │◄──────────────────│  connect()   │
   └──────┬───────┘                   └──────┬───────┘
          │ 回傳「新的」fd                   │
   ┌──────▼───────┐       資料        ┌──────▼───────┐
   │ recv / send  │◄═════════════════►│ send / recv  │
   └──────┬───────┘                   └──────┬───────┘
   ┌──────▼───────┐                   ┌──────▼───────┐
   │   close()    │                   │   close()    │
   └──────────────┘                   └──────────────┘
```

**重點**：`accept()` 回傳一個**新的** file descriptor 代表這條連線；原本的 listening socket
繼續留著，用來接受下一條連線。

## 2. 標頭檔

```c
#define _POSIX_C_SOURCE 200809L  /* 用 -std=c99 編譯時，要加這行才看得到 POSIX 函式 */
#include <sys/types.h>
#include <sys/socket.h>   /* socket, bind, listen, accept, connect, send, recv, setsockopt */
#include <netinet/in.h>   /* struct sockaddr_in, htons, INADDR_ANY */
#include <arpa/inet.h>    /* inet_pton, inet_ntop */
#include <unistd.h>       /* close */
#include <errno.h>
```

## 3. 位址結構

```c
struct sockaddr_in {          /* IPv4 專用 */
    sa_family_t    sin_family;  /* AF_INET */
    in_port_t      sin_port;    /* port，network byte order！ */
    struct in_addr sin_addr;    /* IP，network byte order！ */
    /* ... padding ... */
};
```

`bind` / `connect` / `accept` 的參數型別是通用的 `struct sockaddr *`，所以要轉型：

```c
struct sockaddr_in addr;
memset(&addr, 0, sizeof(addr));           /* 一定要清零 */
addr.sin_family = AF_INET;
addr.sin_port = htons(9000);
addr.sin_addr.s_addr = htonl(INADDR_ANY); /* 0.0.0.0 = 所有網卡 */
bind(fd, (struct sockaddr *)&addr, sizeof(addr));
```

IPv6 用 `struct sockaddr_in6`；要同時支援兩者，用 `struct sockaddr_storage` 或 `getaddrinfo()`。

## 4. Byte order (位元組順序)

多 byte 的整數在記憶體中有兩種存法：

```
0x12345678
big-endian    (網路標準):  12 34 56 78
little-endian (x86, ARM):  78 56 34 12
```

網路協定一律使用 **big-endian（network byte order）**。轉換函式：

| 函式 | 意義 | 用途 |
|------|------|------|
| `htons()` | host to network short (16 bit) | port |
| `htonl()` | host to network long (32 bit) | IPv4 位址 |
| `ntohs()` / `ntohl()` | 反方向 | 從 `accept` 取得的位址轉回來印 |

> **P1 Bug**：`addr.sin_port = port;` 少了 `htons()`。在 big-endian 機器上剛好會動，
> 在 x86 上 port 9000 (`0x2328`) 會變成 10275 (`0x2823`)。

IP 位址字串與二進位互轉：
```c
inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);   /* presentation → network，成功回傳 1 */
char ip[INET_ADDRSTRLEN];
inet_ntop(AF_INET, &addr.sin_addr, ip, sizeof(ip)); /* network → presentation */
```
（舊的 `inet_addr()` / `inet_ntoa()` 不支援 IPv6、而且 `inet_ntoa` 不是 thread-safe，不要用）

## 5. 函式一覽

### `socket()`
```c
int fd = socket(AF_INET, SOCK_STREAM, 0);   /* IPv4 + TCP */
/* AF_INET6 = IPv6；SOCK_DGRAM = UDP；失敗回傳 -1 */
```

### `setsockopt()` 與 `SO_REUSEADDR`
```c
int opt = 1;
setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));   /* 必須在 bind() 之前 */
```
允許 bind 一個還有 TIME_WAIT 連線的 port。**幾乎所有 server 都應該設**。
（`SO_REUSEPORT` 是另一個東西：讓多個 process 同時 bind 同一個 port，由 kernel 做負載平衡）

> Windows 的 `SO_REUSEADDR` 語意不同（允許搶別人正在用的 port），Windows 上的對應是 `SO_EXCLUSIVEADDRUSE`。

### `bind()` / `listen()`
```c
if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); exit(1); }
if (listen(fd, 16) < 0) { perror("listen"); exit(1); }   /* 16 = backlog */
```
常見錯誤：`EADDRINUSE`（port 被佔用或 TIME_WAIT）、`EACCES`（非 root 綁定 < 1024 的 port）。

### `accept()`
```c
struct sockaddr_in cli;
socklen_t len = sizeof(cli);           /* 進去時是 buffer 大小，出來時是實際大小 */
int cfd = accept(fd, (struct sockaddr *)&cli, &len);
/* 不在乎對方位址可以傳 NULL, NULL */
```

### `connect()`
```c
if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) perror("connect");
/* ECONNREFUSED: 對方那個 port 沒有人 listen；ETIMEDOUT: 封包石沉大海 */
```

### `send()` / `recv()`
```c
ssize_t n = send(fd, buf, len, 0);   /* 回傳實際「複製進 send buffer」的 bytes，可能 < len */
ssize_t n = recv(fd, buf, cap, 0);   /* 回傳實際收到的 bytes，可能 < cap */
```

| `recv()` 回傳值 | 意義 |
|-----------------|------|
| `> 0` | 收到 n bytes（**不一定**是對方一次 send 的量） |
| `== 0` | 對方關閉連線（收到 FIN）。**一定要處理，否則會無窮迴圈** |
| `-1` + `errno == EINTR` | 被 signal 打斷，重試即可 |
| `-1` + `errno == EAGAIN/EWOULDBLOCK` | non-blocking socket 目前沒資料 |
| `-1` + `errno == ECONNRESET` | 對方送了 RST（異常中斷） |

`send()` / `recv()` 等同於 `write()` / `read()` 加上 flags 參數；flags 填 0 時效果一樣。

### `close()` / `shutdown()`
```c
close(fd);                 /* 釋放 fd；這是最後一個參照時送出 FIN */
shutdown(fd, SHUT_WR);     /* 只關閉寫方向 (half-close)，還能繼續 recv */
```

## 6. 三個一定要會的「完整」模式

### 6.1 `send_all`：處理 partial send

```c
static int send_all(int fd, const char *buf, size_t len)
{
    size_t sent = 0;
    while (sent < len) {
        ssize_t n = send(fd, buf + sent, len - sent, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        sent += (size_t)n;
    }
    return 0;
}
```

### 6.2 `recv_all`：剛好收 n bytes

```c
static ssize_t recv_all(int fd, char *buf, size_t len)
{
    size_t got = 0;
    while (got < len) {
        ssize_t n = recv(fd, buf + got, len - got, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        if (n == 0) break;      /* 對方關閉，回傳已收到的量 */
        got += (size_t)n;
    }
    return (ssize_t)got;
}
```
（`recv` 有個 `MSG_WAITALL` flag 有類似效果，但被 signal 打斷時仍可能提早返回，不能完全依賴）

### 6.3 Server 主迴圈

```c
for (;;) {
    int cfd = accept(lfd, NULL, NULL);
    if (cfd < 0) {
        if (errno == EINTR) continue;
        perror("accept");
        continue;
    }
    handle_client(cfd);   /* 裡面要處理 recv()==0，最後 close(cfd) */
}
```

## 7. SIGPIPE

對一條「對方已經關閉」的連線 `send()`，第一次可能成功，對方回 RST；
再 `send()` 一次，kernel 會送你 **SIGPIPE**，預設行為是**直接終止 process**——
server 會無聲無息地死掉。

```c
signal(SIGPIPE, SIG_IGN);           /* 全域忽略，send() 改為回傳 -1, errno = EPIPE */
send(fd, buf, len, MSG_NOSIGNAL);   /* 或者每次 send 時指定 (Linux) */
```

（Python 預設就忽略 SIGPIPE，會改 raise `BrokenPipeError`）

## 8. 錯誤處理習慣

```c
if (bind(...) < 0) {
    perror("bind");    /* 會印出 "bind: Address already in use" */
    exit(1);
}
```
- 每一個 socket 系統呼叫都要檢查回傳值
- `perror` / `strerror(errno)` 印出人看得懂的錯誤
- `errno` 只在函式**失敗時**有意義，成功時可能是殘留的舊值

## 9. 同時服務多個 client（P1 的延伸）

P1 是 iterative server：服務完一個才服務下一個。常見改法：

```c
/* fork 版：每條連線一個 process */
signal(SIGCHLD, SIG_IGN);              /* 自動回收子 process，避免 zombie */
for (;;) {
    int cfd = accept(lfd, NULL, NULL);
    if (cfd < 0) continue;
    pid_t pid = fork();
    if (pid == 0) {          /* child */
        close(lfd);          /* child 不需要 listening socket */
        handle_client(cfd);
        _exit(0);
    }
    close(cfd);              /* parent 一定要關掉，否則連線永遠不會結束 */
}
```

其他方法（pthread、select/poll/epoll）見 [05-concurrency-models.md](05-concurrency-models.md)。

## 10. 練習

1. 不設定 `SO_REUSEADDR`，啟動 server → 用 `nc` 連線 → Ctrl+C 關掉 server → 立刻重啟，觀察錯誤訊息；再用 `ss -tan | grep TIME-WAIT` 看看
2. 把 P1 server 改成 fork 版本，用三個 `nc` 同時連線測試
3. 用 `getaddrinfo()` 改寫 client，讓它能接受 `localhost` 這種主機名稱，並同時支援 IPv4/IPv6
