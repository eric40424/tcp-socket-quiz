# 06. 除錯工具與常見錯誤

> 上機考時間有限，「能快速看出哪裡壞了」比「寫得快」更重要。

## 1. `nc` (netcat)：萬用的 TCP 瑞士刀

```bash
nc 127.0.0.1 9000                 # 當 client：連上去，打字送出，收到的印出來
nc -l 9000                        # 當 server：listen 在 9000 (OpenBSD 版)
printf 'alice\nhello\n' | nc -q1 127.0.0.1 9000   # 送完等 1 秒再關
nc -zv 127.0.0.1 9000             # 只檢查 port 有沒有開
```

測 P1：`./server 9000` + `nc 127.0.0.1 9000`
測 P3：開三個終端機各跑 `nc 127.0.0.1 9000`，第一行輸入暱稱

在 Windows 上可以用 PowerShell 的 `Test-NetConnection 127.0.0.1 -Port 9000` 檢查 port。

## 2. `ss` / `netstat`：看連線狀態

```bash
ss -tlnp                 # t=TCP l=listening n=不解析名稱 p=顯示 process
ss -tan                  # 所有 TCP 連線與狀態
ss -tan state time-wait  # 只看 TIME_WAIT
ss -tni                  # 加上 RTT、cwnd、send/recv queue 等內部資訊
```

輸出中的 `Recv-Q` / `Send-Q`：
- 一般連線：`Recv-Q` 是還沒被應用程式 `recv()` 的資料量、`Send-Q` 是還沒被對方 ack 的資料量
- listening socket：`Recv-Q` 是 accept queue 裡等著被 `accept()` 的連線數

**常見診斷：**
| 看到 | 可能原因 |
|------|---------|
| 沒有你的 port 在 LISTEN | bind/listen 沒成功、port 寫錯（例如忘了 `htons`！） |
| LISTEN 的 Recv-Q 一直增加 | server 沒在 `accept()`（卡在處理別的 client？） |
| 某條連線 Recv-Q 很大 | 應用程式沒在 `recv()` |
| 大量 CLOSE_WAIT | 程式收到 EOF 後忘了 `close()` |
| 大量 TIME_WAIT | 正常現象（主動關閉方），量很大時考慮連線重用 |

## 3. `tcpdump` / Wireshark：看真正的封包

```bash
sudo tcpdump -i lo -nn 'tcp port 9000'          # 看 loopback 上 port 9000 的封包
sudo tcpdump -i lo -nn -X 'tcp port 9000'       # 加上 hex + ASCII 內容
sudo tcpdump -i lo -w cap.pcap 'tcp port 9000'  # 存檔，之後用 Wireshark 開
```

讀懂 tcpdump 輸出：

```
IP 127.0.0.1.54321 > 127.0.0.1.9000: Flags [S], seq 1000            ← SYN
IP 127.0.0.1.9000 > 127.0.0.1.54321: Flags [S.], seq 2000, ack 1001 ← SYN+ACK
IP 127.0.0.1.54321 > 127.0.0.1.9000: Flags [.], ack 2001            ← ACK
IP 127.0.0.1.54321 > 127.0.0.1.9000: Flags [P.], seq 1001:1007, length 6  ← 資料 (PSH)
IP 127.0.0.1.9000 > 127.0.0.1.54321: Flags [F.], ...                ← FIN
IP 127.0.0.1.9000 > 127.0.0.1.54321: Flags [R], ...                 ← RST
```

| Flag | 意義 |
|------|------|
| `S` | SYN |
| `.` | ACK |
| `P` | PSH（有資料，請盡快交給應用程式） |
| `F` | FIN |
| `R` | RST（重置連線：對方 port 沒人聽、或程式異常關閉） |

Wireshark 的 filter：`tcp.port == 9000`、`tcp.flags.reset == 1`；右鍵 → Follow → TCP Stream 可以看到整段對話。

## 4. `strace`：看程式呼叫了哪些系統呼叫

```bash
strace -f -e trace=network ./server 9000
strace -f -e trace=socket,bind,listen,accept,recvfrom,sendto ./server 9000
```

輸出範例：
```
socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 3
bind(3, {sa_family=AF_INET, sin_port=htons(10275), ...}, 16) = 0   ← port 不對！
listen(3, 16) = 0
```

上面這個例子一眼就能看出 P1 的 `htons` bug。strace 也是找「程式卡在哪」的好工具：
卡住的程式最後一行通常是 `accept(...` 或 `recvfrom(...` 沒有回傳值。

## 5. 常見錯誤訊息速查

| 錯誤 | errno | 常見原因 | 解法 |
|------|-------|---------|------|
| Address already in use | `EADDRINUSE` | port 被佔用 / TIME_WAIT | `SO_REUSEADDR`；`ss -tlnp` 找出誰在用 |
| Connection refused | `ECONNREFUSED` | 目標 port 沒有人 listen（對方回 RST） | 確認 server 有啟動、port 正確 |
| Connection reset by peer | `ECONNRESET` | 對方異常關閉、或關閉時還有沒讀的資料 | 視為斷線處理 |
| Broken pipe | `EPIPE` | 寫入已關閉的連線 | 忽略 SIGPIPE，視為斷線 |
| Connection timed out | `ETIMEDOUT` | 封包到不了（防火牆、IP 錯誤） | 檢查網路與防火牆 |
| Permission denied | `EACCES` | 非 root 綁定 < 1024 的 port | 換一個大於 1024 的 port |
| Bad file descriptor | `EBADF` | 用了已關閉或未初始化的 fd | 檢查 `close` 的時機，fd 是否為 -1 |
| Invalid argument | `EINVAL` | 例如對沒有 `listen()` 的 socket 呼叫 `accept()` | 檢查呼叫順序 |
| Resource temporarily unavailable | `EAGAIN` | non-blocking 時沒有資料 / buffer 滿 | 這是正常的，等下次 select |
| Too many open files | `EMFILE` | fd 用完（忘記 close，或連線太多） | 修 fd leak；`ulimit -n` |

## 6. 除錯流程建議

```
程式沒反應？
 ├─ server 有在 LISTEN 嗎？                         → ss -tlnp
 │    └─ 沒有 → 看 bind/listen 的錯誤訊息；strace 看 port
 ├─ client 連得上嗎？                                → nc -zv
 ├─ 資料有送出去嗎？                                  → tcpdump
 ├─ 程式卡在哪個系統呼叫？                             → strace -p <pid>
 └─ 有沒有一直在跑但不做事（CPU 100%）？              → top；檢查 busy loop
```

judge 的 `-v` 參數會在失敗時印出 server 的輸出，記得在 server 裡多印 log（但 C 記得 `fflush(stdout)`）。

## 7. 在 judge 環境之外重現問題

judge 的每個測試都只是普通的 socket 操作，你可以在 Python REPL 裡手動重現：

```python
import socket, struct, json
s = socket.create_connection(("127.0.0.1", 9100))
req = json.dumps({"op": "GET", "key": "a"}).encode()
s.sendall(struct.pack("!I", len(req)) + req)
n, = struct.unpack("!I", s.recv(4)); print(s.recv(n))
```
