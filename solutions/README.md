# 參考解答與解析

> 考完再看！解答程式碼在同資料夾的 `p1_echo/` ~ `p4_kvstore/`，裡面用 `TODO x-x` 與 `[BUG 修正]` 標出修改處。

---

## P1：Echo Server / Client

### TODO

| 編號 | 解答 | 重點 |
|------|------|------|
| 1-A | `socket(AF_INET, SOCK_STREAM, 0)` | `AF_INET` = IPv4，`SOCK_STREAM` = TCP |
| 1-B | `setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt))` | 必須在 `bind()` **之前**設定 |
| 1-C | `bind(fd, (struct sockaddr *)&addr, sizeof(addr))` → `listen(fd, BACKLOG)` | `sockaddr_in` 要轉型成通用的 `sockaddr *` |
| 1-D | `accept(listen_fd, (struct sockaddr *)&cli, &cli_len)` | 第三個參數是**指標**（value-result argument） |
| 1-E | `send(fd, buf + sent, len - sent, 0)` | 從「還沒送的地方」開始送 |
| 1-F | `socket` → 填 `sockaddr_in` (`htons`, `inet_pton`) → `connect` | |
| 1-G | 迴圈 `recv` 直到收滿 `len` bytes，`n == 0` 代表對方關閉 | 一次 `recv` 不保證收到完整一行 |

### 🐞 Bug 1：`addr.sin_port = port;`

port 必須是 **network byte order (big-endian)**。x86 是 little-endian，9000 (`0x2328`)
不轉換的話會變成 `0x2823` = 10275，server 實際上監聽在錯的 port。
修正：`addr.sin_port = htons((uint16_t)port);`

### 🐞 Bug 2：`handle_client` 沒處理 `recv()` 回傳 0

`recv()` 回傳 0 代表對方送了 FIN（正常關閉）。原本的程式會呼叫 `send_all(fd, buf, 0)`
然後再 `recv()`，又拿到 0……**無窮迴圈**，第二個 client 永遠等不到服務。
修正：`if (n == 0) break;`

### 為什麼 judge 的 client 測試會抓到 1-G 原本的寫法？

judge 的測試 server 會把資料每 7 bytes 切一塊、間隔 3ms 送出。原本的寫法只 `recv()` 一次，
收到的只是一部分，剩下的資料會在下一輪才被讀到，最後一行的尾巴則永遠不會被讀出來。

---

## P2：Framing

### 🐞 Bug：`struct.Struct("I")`

`"I"` 是 **native byte order + native alignment**，在 x86 上是 little-endian，
`b"hello"` 的 header 變成 `b"\x05\x00\x00\x00"`。網路協定要用 `"!I"`（或 `">I"`）。

| 格式字元 | byte order | 大小/對齊 |
|----------|-----------|-----------|
| `@` (預設) | native | native |
| `=` | native | standard |
| `<` | little-endian | standard |
| `>` / `!` | big-endian | standard |

### `recv_msg` 怎麼區分「正常結束」與「中途斷線」？

先單獨 `recv` 一次 header：如果一個 byte 都沒拿到 → 對方在訊息之間關閉 → `None`；
如果拿到一部分 → 用 `recv_exact` 補齊，這時候再斷線就是 `ConnectionError`。

```python
first = sock.recv(HEADER.size)
if not first:
    return None
header = first + recv_exact(sock, HEADER.size - len(first))
```

### 常見錯誤
- `recv_exact` 用 `sock.recv(65536)` 讀 → **多讀**到下一則訊息的資料，然後被丟掉
- 空訊息回傳 `None` → 呼叫端以為連線結束了
- 先 `recv_exact(length)` 再檢查 `MAX_MSG_SIZE` → 攻擊者送一個 `0xFFFFFFFF` 的 header 就能讓你配置 4 GiB
- 用 `send` 而不是 `sendall`

---

## P3：Chat Server

### 🐞 Bug：`broadcast` 忽略了 `exclude`，也沒跳過還沒設定暱稱的連線

```python
for c in list(self.clients.values()):
    if c is exclude or c.nick is None:
        continue
    self.send(c, text)
```

### TODO 重點

- **3-C 切行**：`while b"\n" in inbuf and not client.closed:`。`not client.closed` 很重要——
  `/quit` 之後同一個封包裡剩下的行不能再處理（judge 有測）。
- **3-D / 3-E 寫入事件的開關**：socket 的 send buffer 幾乎永遠有空間，所以一直監聽
  `EVENT_WRITE` 的話 `select()` 會不斷立刻返回 → CPU 100%（busy loop）。
  正確作法是**有資料要送才監聽，送完就取消**。
- **為什麼不能在 `send()` 裡直接 `sendall()`？** non-blocking socket 的 send buffer 滿了，
  `sendall` 會 raise `BlockingIOError`，而且你不知道送出去了多少。
  如果改成 blocking，一個不讀資料的 client 就能卡住整個 server。
- **3-F 的順序**：先把自己從 `self.clients` 移除再 `broadcast`，否則會送給已經關閉的 socket。

---

## P4：KV Server

### 🐞 Bug：`with threading.Lock():`

每次呼叫都**建立一把新的鎖**，每個 thread 都拿到自己專屬的鎖，等於沒鎖。必須用共用的 `self.lock`。

read-modify-write（讀 → 算 → 寫回）不是 atomic 的：

```
Thread A: cur = data["c"]   # 0
Thread B: cur = data["c"]   # 0
Thread A: data["c"] = 1
Thread B: data["c"] = 1     # A 的更新不見了 (lost update)
```

`_simulate_disk_latency()` 把讀和寫之間的時間拉長，讓 race condition 幾乎必定發生。
就算刪掉它，bug 仍然存在，只是變得很難重現——這才是最可怕的地方。

### TODO 4-B 的例外處理順序

```python
try:
    req = recv_json(conn)
except socket.timeout:         # ① OSError 的子類別，要放最前面
    break
except ValueError:             # ② JSONDecodeError / UnicodeDecodeError，訊息已完整讀完 → 繼續服務
    resp = error("bad request")
except (ConnectionError, ProtocolError, OSError):   # ③
    break
```

為什麼 JSON 錯誤可以繼續服務，但 `ProtocolError` 要斷線？
因為 JSON 錯誤時整則訊息已經依 length 讀完，**串流還是對齊的**；
`ProtocolError`（length 太大）時我們沒有讀 payload，串流已經錯位，無法再繼續解析。

### 進階
- 一條連線一個 thread，連線數一多會吃光記憶體（每條 thread 預設數 MB stack）→ 可以考慮 thread pool 或 asyncio
- 一把全域鎖會讓所有操作序列化 → 可以用 lock striping（依 key 的 hash 分成多把鎖）
