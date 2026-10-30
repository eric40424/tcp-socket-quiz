# TCP Socket 程式設計 上機考 試題本

> 模擬成大資工特選上機考形式：拿到一份「寫到一半、還有 bug」的專案，
> 在時限內補完 TODO、修好 bug，用自動評分程式 (judge) 驗證，judge 給的分數就是你的成績。

---

## 考試規則

| 項目 | 說明 |
|------|------|
| 時間 | 4 小時 |
| 語言 | C (C99)、Python 3.10+ (只能用標準函式庫) |
| 環境 | Ubuntu 22.04 (可以用專案附的 `Dockerfile`)、gcc、bash |
| 可查資料 | `man` page、Python 官方文件、搜尋引擎 |
| 禁止 | 安裝套件、與他人交談、**偷看 `solutions/`** |
| 評分 | `python3 judge/judge.py`，可以無限次重跑 |
| 同分時 | 先完成的人排前面 (原考試的計分方式：`分數 = 解題分 + (1 − 完成次序 / 人數)`) |

**作答範圍**：只能修改 `problems/` 底下的檔案。judge 會檢查程式的 **行為**，不會比對寫法，
所以只要符合規格，怎麼實作都可以。

**注意**：除了標示 `TODO` 的地方，每一題的程式碼裡還**藏有 bug**（數量寫在題目說明裡）。
只補 TODO 沒有修 bug，是拿不到滿分的。

---

## 配分總覽

| 題號 | 主題 | 語言 | 配分 | 檔案 |
|------|------|------|------|------|
| P1 | Echo Server / Client | C | 25 | `problems/p1_echo/server.c`, `client.c` |
| P2 | 訊息邊界 (Framing) | Python | 20 | `problems/p2_framing/protocol.py` |
| P3 | 非阻塞多人聊天室 | Python | 30 | `problems/p3_chat/chat_server.py` |
| P4 | 多執行緒 Key-Value Server | Python | 25 | `problems/p4_kvstore/kv_server.py` |
| | **合計** | | **100** | |

> P4 會 `import` P2 寫的 `protocol.py`。**P2 沒寫好，P4 也會一起掛掉**，建議照順序寫。

---

## P1：Echo Server / Client (C，25 分)

### 情境

你接手了一個學長寫到一半的 echo server：client 送來什麼，server 就原封不動回傳。
學長說「在我電腦上可以跑」，但它連編譯後都連不上。

### 規格

**server** — `./server <port>`
1. 監聽 `0.0.0.0:<port>`，成功 `listen()` 之後印出一行包含 `listening` 的訊息
2. 一次服務一個 client（iterative server），收到的資料原封不動送回
3. client 關閉連線後，要能繼續 `accept()` 下一個 client
4. 能正確回傳大量資料（1 MiB）
5. server 被關掉後**立刻**重新啟動，必須能 bind 同一個 port

**client** — `./client <ipv4-address> <port>`
1. 從 stdin 一行一行讀取，送給 server
2. 把 server 回傳的資料**完整地**印到 stdout（stdout 只能有 server 回傳的資料）
3. stdin 結束後關閉連線，exit code 為 0

### 要做的事

| 編號 | 檔案 | 內容 |
|------|------|------|
| TODO 1-A | server.c | 建立 IPv4 TCP socket |
| TODO 1-B | server.c | 設定 `SO_REUSEADDR` |
| TODO 1-C | server.c | `bind()` + `listen()` |
| TODO 1-D | server.c | `accept()` |
| TODO 1-E | server.c | 完成 `send_all()` |
| TODO 1-F | client.c | 建立 socket 並 `connect()` |
| TODO 1-G | client.c | 改寫錯誤的接收邏輯 |
| 🐞 × 2 | server.c | 藏有 2 個 bug |

### 評分項目

| 測試 | 分數 |
|------|------|
| `gcc -std=c99` 編譯成功 | 3 |
| 基本 echo | 5 |
| 1 MiB 大量資料 echo | 5 |
| 第一個 client 離開後能服務下一個 | 4 |
| server 重啟後能立刻 bind 同一個 port | 3 |
| client 能正確處理分段抵達的資料 | 5 |

### 提示
- `man 2 socket`、`man 2 bind`、`man 7 tcp`、`man 7 socket`
- 手動測試：`make && ./server 9000`，另開終端機 `nc 127.0.0.1 9000` 或 `./client 127.0.0.1 9000`
- 「在本機手動測試看起來沒問題」不代表是對的，judge 的測試 server 會**故意把資料切成很小塊、慢慢回傳**

---

## P2：訊息邊界 Length-prefixed Framing (Python，20 分)

### 情境

TCP 是 **byte stream**，沒有「一則訊息」的概念。對方 `send()` 了兩次，你可能一次 `recv()`
就全部收到（黏包），也可能要 `recv()` 好幾次才收齊一則（半包）。
我們要在 TCP 上面自己定義訊息邊界。

### 線上格式

```
+-------------------+---------------------------+
| length (4 bytes)  | payload (length bytes)    |
| uint32 big-endian |                           |
+-------------------+---------------------------+
```

例：`b"hello"` → `b"\x00\x00\x00\x05hello"`；空訊息 `b""` → `b"\x00\x00\x00\x00"`

### 要做的事

| 編號 | 函式 | 規格 |
|------|------|------|
| TODO 2-A | `recv_exact(sock, n)` | 剛好讀 n bytes；不可多讀；讀滿前連線關閉 → `ConnectionError` |
| TODO 2-B | `send_msg(sock, payload)` | 送出 header + payload；超過 `MAX_MSG_SIZE` → `ProtocolError` |
| TODO 2-C | `recv_msg(sock)` | 收一則訊息；訊息之間正常關閉 → `None`；訊息中途關閉 → `ConnectionError`；長度超過上限 → `ProtocolError` |
| 🐞 × 1 | | 藏有 1 個 bug |

### 評分項目

| 測試 | 分數 |
|------|------|
| `send_msg` 的線上格式 | 3 |
| `recv_exact` 拼湊分段資料、不多讀 | 3 |
| `recv_exact` 資料不足時 → `ConnectionError` | 2 |
| 黏包（一次收到多則訊息，含空訊息） | 3 |
| 半包（一個 byte 一個 byte 抵達） | 3 |
| EOF 處理 | 2 |
| length 過大 → `ProtocolError` | 2 |
| 5 MiB 訊息與 JSON 往返 | 2 |

---

## P3：非阻塞多人聊天室 (Python，30 分)

### 情境

做一個**單執行緒**的聊天室 server，用 `selectors` 同時處理很多連線。
不能開 thread，所有 socket 都必須是 non-blocking。

### 協定（純文字、UTF-8、一行以 `\n` 結尾）

| client 送出 | server 的動作 |
|-------------|---------------|
| 連線後的第一行 `<nick>` | 設定暱稱，廣播 `* <nick> joined\n` 給**其他人** |
| 一般訊息 `<text>` | 廣播 `[<nick>] <text>\n` 給**其他人**（不含自己） |
| `/who` | 只回給自己：`* online: <暱稱依字母排序，以 ", " 分隔>\n` |
| `/quit` | 關閉這條連線，廣播 `* <nick> left\n`；同一包裡 `/quit` 後面的內容要忽略 |
| （直接斷線） | 廣播 `* <nick> left\n` |

- 還沒送出暱稱的連線**不算在線上**，不會收到任何廣播
- 行尾的 `\r` 要去掉（相容 `telnet` / Windows）

### 要做的事

| 編號 | 位置 | 內容 |
|------|------|------|
| TODO 3-A | `__init__` | 把 listening socket 註冊到 selector |
| TODO 3-B | `_accept` | accept → non-blocking → 註冊 |
| TODO 3-C | `_on_readable` | 從 buffer 切出完整的行 |
| TODO 3-D | `send` | 開始監聽 `EVENT_WRITE` |
| TODO 3-E | `_on_writable` | 送完後取消 `EVENT_WRITE` |
| TODO 3-F | `_disconnect` | 清理連線、廣播離開訊息 |
| 🐞 × 1 | | 藏有 1 個 bug |

### 評分項目

| 測試 | 分數 |
|------|------|
| 加入通知（暱稱分段抵達） | 4 |
| 廣播給其他人、不含自己 | 4 |
| 一次收到多行與不完整的行 | 4 |
| `/who` 只回給自己 | 3 |
| 尚未設定暱稱的連線不會收到廣播 | 3 |
| `/quit` | 4 |
| client 直接斷線 | 3 |
| 30 個 client 同時聊天 | 3 |
| 閒置時不會空轉（CPU 使用率，僅 Linux） | 2 |

### 提示
- 手動測試：`python3 chat_server.py 9000`，再開幾個 `python3 chat_client.py 127.0.0.1 9000` 或 `nc 127.0.0.1 9000`
- 為什麼不能在 `send()` 裡直接 `sock.sendall()`？想想看 non-blocking socket 的 send buffer 滿了會怎樣

---

## P4：多執行緒 Key-Value Server (Python，25 分)

### 情境

做一個迷你版 Redis。每條連線一個 thread，使用 P2 的 length-prefixed JSON 溝通。

### Request / Response

| Request | Response |
|---------|----------|
| `{"op":"SET","key":k,"value":v}` | `{"ok":true}` |
| `{"op":"GET","key":k}` | `{"ok":true,"value":v}`；不存在 → `{"ok":false,"error":"..."}` |
| `{"op":"DEL","key":k}` | `{"ok":true,"deleted":true/false}` |
| `{"op":"INCR","key":k,"by":n}` | `{"ok":true,"value":新值}`；`by` 預設 1；不存在視為 0；原值不是整數 → `ok:false` |
| 未知 op、不合法的 JSON | `{"ok":false,"error":"..."}`，**連線不可以斷** |

其他需求：
- 同時服務多個 client
- client 超過 `--idle-timeout` 秒沒送資料 → server 主動斷線
- 多個 client 同時 `INCR` 同一個 key，結果必須正確

### 要做的事

| 編號 | 位置 | 內容 |
|------|------|------|
| TODO 4-A | `serve` | 每個連線開一條 thread |
| TODO 4-B | `handle_conn` | request/response 迴圈、逾時、錯誤處理 |
| TODO 4-C | `handle_request` | 實作 `DEL` |
| 🐞 × 1 | | 藏有 1 個 bug |

### 評分項目

| 測試 | 分數 |
|------|------|
| SET / GET | 4 |
| GET 不存在的 key 與 DEL | 3 |
| 錯誤的 request 不中斷連線 | 3 |
| INCR | 3 |
| 同時服務多個 client | 4 |
| 10 個 client 同時 INCR（race condition） | 5 |
| 閒置逾時 | 3 |

---

## 加分思考題（不計分，口試可能會問）

1. P1 的 server 一次只能服務一個 client，有哪些方法可以改成同時服務多個？各自的優缺點？
2. P3 如果有一個 client 只連線、從來不 `recv()`，其他人一直講話，server 會發生什麼事？要怎麼防範？
3. P4 的 thread-per-connection 模型在 10,000 個連線時會遇到什麼問題？
4. 為什麼 P2 要設 `MAX_MSG_SIZE`？拿掉會有什麼安全問題？
5. judge 測試「server 重啟」時，TIME_WAIT 是出現在 server 端還是 client 端？為什麼？
