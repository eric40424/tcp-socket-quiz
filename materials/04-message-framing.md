# 04. 訊息邊界 (Message Framing)

> TCP 給你的是一條 byte 的水管，不是一個一個的信封。
> 「一則訊息從哪裡開始、到哪裡結束」必須由應用層協定自己定義。這是 P2 的核心。

## 1. 問題重現

```python
# sender
sock.sendall(b"hello")
sock.sendall(b"world")

# receiver：以下每一種結果都是合法的
sock.recv(1024)  → b"helloworld"             # 黏包
sock.recv(1024)  → b"hel", 之後 b"loworld"   # 半包 + 黏包
sock.recv(1024)  → b"hello", 之後 b"world"   # 你「期待」的結果，但只是剛好
```

在 localhost 上測試，幾乎總是得到第三種結果，於是程式「看起來」是對的。
上了真實網路（或碰到 judge 故意把資料切碎）才會出錯。

## 2. 三種常見的切分方法

### 2.1 固定長度

每則訊息都剛好 N bytes。簡單，但浪費空間、不能放可變長度資料。
適合：固定格式的二進位封包（例如某些遊戲、感測器資料）。

### 2.2 分隔符號 (delimiter)

用特殊字元標示結尾，最常見是 `\n` 或 `\r\n`。

```
NICK alice\n
hello everyone\n
```

- 優點：人類可讀，可以用 `nc` / `telnet` 直接測試
- 缺點：payload 裡不能出現分隔符號（或需要跳脫）；必須逐 byte 掃描
- 實例：HTTP header、SMTP、Redis 的 RESP 協定、**P3 聊天室**

接收端的標準寫法：

```python
buffer = b""
while True:
    data = sock.recv(4096)
    if not data:
        break
    buffer += data
    while b"\n" in buffer:
        line, buffer = buffer.split(b"\n", 1)   # 只切第一個
        handle(line)
    # 迴圈結束時，buffer 裡可能還有「不完整的一行」，留到下一輪
```

別忘了限制 buffer 長度：惡意 client 送 1GB 都不換行，你的記憶體就爆了。

### 2.3 長度前綴 (length-prefix)

先送固定大小的 header 表示 payload 長度，再送 payload。

```
+-------------------+---------------------------+
| length (4 bytes)  | payload (length bytes)    |
+-------------------+---------------------------+
00 00 00 05  68 65 6c 6c 6f       →  b"hello"
00 00 00 00                       →  b""  (空訊息)
```

- 優點：payload 可以是任意二進位資料；接收端知道要讀多少，不用掃描
- 缺點：人類不可讀；header 錯一個 byte 整條串流就錯位了
- 實例：**P2 / P4**、TLS record、HTTP/2 frame、gRPC、Kafka、PostgreSQL 協定

HTTP/1.1 其實是**混合**：header 用 `\r\n\r\n` 分隔，body 用 `Content-Length`（長度前綴）或 `chunked` 編碼。

## 3. Length-prefix 的完整實作

```python
import struct

HEADER = struct.Struct("!I")       # 4 bytes, big-endian, unsigned
MAX_MSG_SIZE = 16 * 1024 * 1024

def send_msg(sock, payload: bytes):
    if len(payload) > MAX_MSG_SIZE:
        raise ValueError("too large")
    sock.sendall(HEADER.pack(len(payload)) + payload)

def recv_exact(sock, n):
    chunks, remaining = [], n
    while remaining:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionError("closed in the middle of a message")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)

def recv_msg(sock):
    first = sock.recv(HEADER.size)
    if not first:
        return None                        # 在訊息與訊息之間正常關閉
    header = first + recv_exact(sock, HEADER.size - len(first))
    (length,) = HEADER.unpack(header)
    if length > MAX_MSG_SIZE:
        raise ValueError("too large")      # 先檢查，再讀！
    return recv_exact(sock, length)
```

### 每一行背後的考量

| 細節 | 為什麼 |
|------|--------|
| `"!I"` 而不是 `"I"` | 雙方的 CPU 可能 endian 不同，網路協定一律 big-endian |
| `recv(min(remaining, ...))` | 只讀「還缺的量」，不然會吃掉下一則訊息的開頭 |
| 區分 `None` 與 `ConnectionError` | 呼叫端需要知道是「正常結束」還是「傳輸失敗」 |
| 空訊息回傳 `b""` 不是 `None` | `b""` 和「連線結束」是兩回事，`if not msg` 會把兩者混為一談 |
| 讀 payload 前檢查 `MAX_MSG_SIZE` | 否則對方送 `FF FF FF FF` 就能讓你嘗試配置 4 GiB 記憶體 (DoS) |
| header + payload 一次 `sendall` | 減少系統呼叫，也避免 Nagle + delayed ACK 造成延遲 |

## 4. 串流錯位 (desync)

一旦你多讀或少讀了任何一個 byte，之後所有的 header 都會被解讀成錯誤的長度。
這就是為什麼 P4 在遇到 `ProtocolError` 時必須**斷線**：

| 錯誤 | 串流狀態 | 處理方式 |
|------|---------|---------|
| payload 不是合法 JSON | 已依 length 讀完整則訊息，**仍然對齊** | 回錯誤訊息，繼續服務 |
| length 超過上限 | payload 沒讀，**已經錯位** | 只能斷線 |
| 讀到一半逾時 | 不知道讀到哪，**已經錯位** | 只能斷線 |

## 5. 在 framing 之上：序列化格式

framing 決定「一則訊息的邊界」，序列化決定「訊息內容怎麼表示」：

| 格式 | 特性 |
|------|------|
| JSON | 人類可讀、通用，但體積大、沒有 schema、不能直接放二進位資料 |
| MessagePack / CBOR | 二進位的 JSON，較小較快 |
| Protocol Buffers / FlatBuffers | 有 schema、跨語言、向後相容、體積小 |
| 自訂二進位 (`struct`) | 最省空間，但演進困難 |

P4 使用「length-prefix + JSON」，是很多內部 RPC 的實際做法。

## 6. 練習

1. 用 C 寫一個與 P2 相容的 `send_msg` / `recv_msg`，並用 Python 的 P2 實作和它互傳訊息
2. 修改協定：header 改成 `type (1 byte) + length (4 bytes)`，用 type 區分 JSON 與二進位檔案
3. 如果要支援超過 4 GiB 的訊息，你會怎麼修改格式？（提示：`Q`、或 varint）
