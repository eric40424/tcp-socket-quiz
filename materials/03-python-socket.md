# 03. Python socket 程式設計

> Python 的 `socket` 模組幾乎是 C API 一對一的包裝，所以 02 學到的觀念全部適用。
> 差別在於：錯誤變成 exception、位址變成 tuple、不需要手動處理 byte order 的位址轉換。

## 1. C 與 Python 對照

| C | Python |
|---|--------|
| `socket(AF_INET, SOCK_STREAM, 0)` | `socket.socket(socket.AF_INET, socket.SOCK_STREAM)` |
| `setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, ...)` | `s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)` |
| `bind(fd, &addr, len)` + `htons` | `s.bind(("0.0.0.0", 9000))` |
| `listen(fd, 16)` | `s.listen(16)` |
| `accept(fd, &cli, &len)` | `conn, (ip, port) = s.accept()` |
| `connect(fd, &addr, len)` | `s.connect(("127.0.0.1", 9000))` |
| `send` / `recv` | `s.send(b)` / `s.recv(n)` |
| 自己寫的 `send_all` | **`s.sendall(b)`** |
| `recv() == 0` | `s.recv(n) == b""` |
| `errno == EINTR` | Python 3.5+ 自動重試 (PEP 475) |
| `errno == EAGAIN` | `BlockingIOError` |
| `errno == ECONNRESET` | `ConnectionResetError` |
| `errno == EPIPE` | `BrokenPipeError` |
| `errno == ECONNREFUSED` | `ConnectionRefusedError` |
| `close(fd)` | `s.close()` 或 `with s:` |

## 2. 最小的 echo server / client

```python
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as lsock:
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", 9000))
    lsock.listen()
    while True:
        conn, addr = lsock.accept()
        with conn:
            print("connected", addr)
            while True:
                data = conn.recv(4096)
                if not data:          # b"" → 對方關閉
                    break
                conn.sendall(data)
```

```python
import socket

with socket.create_connection(("127.0.0.1", 9000), timeout=5) as s:
    s.sendall(b"hello\n")
    print(s.recv(4096))       # ⚠ 不保證收到完整的 b"hello\n"！
```

`socket.create_connection()` 會處理主機名稱解析、IPv4/IPv6，比手動 `connect` 方便。
`socket.create_server(("", 9000))`（3.8+）也會自動幫你設 `SO_REUSEADDR`（POSIX 上）。

## 3. `send` vs `sendall`

```python
n = s.send(data)     # 回傳實際送出的 bytes，可能 < len(data)
s.sendall(data)      # 迴圈送到完為止，失敗 raise exception；成功回傳 None
```

**blocking socket 一律用 `sendall`**。`send` 只在 non-blocking 情境（P3）中使用，
因為你需要知道送出了多少、剩下的存起來。

> 用 `sendall` 時如果 socket 有設定 timeout 而逾時了，你**無法得知**送出了多少。

## 4. `recv` 永遠可能「不夠」

`recv(4096)` 的意思是「**最多**給我 4096 bytes」，可能只給你 1 byte。
需要固定長度的資料時，自己寫迴圈：

```python
def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))   # 只要求「還缺的量」，避免多讀
        if not chunk:
            raise ConnectionError("connection closed early")
        buf += chunk
    return bytes(buf)
```

> 用 `bytes +=` 在迴圈裡拼接是 O(n²)；資料大時用 `bytearray` 或 list + `b"".join()`。

## 5. 以行為單位的資料：`makefile()`

把 socket 包成 file-like 物件，就能用 `readline()` 或 `for line in f`：

```python
with conn.makefile("r", encoding="utf-8", newline="\n") as f:
    for line in f:          # 自動處理半包、黏包
        handle(line.rstrip("\n"))
```

方便，但只適用於 **blocking** socket。P3 是 non-blocking，必須自己切行。

## 6. Timeout

```python
s.settimeout(5.0)     # 之後的 recv/send/accept/connect 超過 5 秒 raise socket.timeout
s.settimeout(None)    # blocking (預設)
s.settimeout(0)       # 等同 setblocking(False)
```

- Python 3.10 起 `socket.timeout` 是 `TimeoutError` 的別名，而 `TimeoutError` 是 `OSError` 的子類別
- 所以 `except OSError` 會**吃掉** timeout。需要區分的話，`except socket.timeout` 要寫在前面（P4 TODO 4-B）
- 逾時後 socket 的狀態可能不確定（例如讀到一半的訊息），通常應該直接關閉連線

```python
try:
    data = conn.recv(4096)
except socket.timeout:
    ...            # 閒置太久
except ConnectionResetError:
    ...            # 對方 RST
except OSError as e:
    ...            # 其他錯誤
```

## 7. 例外階層 (節錄)

```
OSError
 ├── BlockingIOError           (EAGAIN / EWOULDBLOCK)
 ├── InterruptedError          (EINTR，3.5 後很少見)
 ├── TimeoutError  (= socket.timeout)
 └── ConnectionError
      ├── BrokenPipeError       (EPIPE)
      ├── ConnectionAbortedError
      ├── ConnectionRefusedError (ECONNREFUSED)
      └── ConnectionResetError   (ECONNRESET)
```

## 8. bytes 與 str

socket 只認識 **bytes**。

```python
s.sendall("你好\n".encode("utf-8"))      # str → bytes
text = data.decode("utf-8")               # bytes → str
```

⚠ 不要對**半包**做 decode：一個中文字在 UTF-8 是 3 bytes，可能剛好被切成兩半 →
`UnicodeDecodeError`。正確作法是先用 bytes 切出完整的訊息/行，再 decode（P3 就是這樣做的）。

## 9. `struct`：打包二進位資料

```python
import struct
struct.pack("!I", 5)            # b'\x00\x00\x00\x05'   ! = network byte order
struct.pack("<I", 5)            # b'\x05\x00\x00\x00'   < = little-endian
struct.unpack("!I", b"\x00\x00\x00\x05")   # (5,)  注意回傳 tuple
H = struct.Struct("!HI")        # 預先編譯：unsigned short + unsigned int
H.size                           # 6
```

| 字元 | C 型別 | 大小 (standard) |
|------|--------|----------------|
| `B` | unsigned char | 1 |
| `H` | unsigned short | 2 |
| `I` | unsigned int | 4 |
| `Q` | unsigned long long | 8 |
| `s` | char[] | 指定長度，如 `16s` |

> **P2 Bug**：沒加 `!` 的 `"I"` 是 native byte order，在 x86 上就是 little-endian。

## 10. 多執行緒基礎

```python
import threading

def handle(conn, addr):
    with conn:
        ...

while True:
    conn, addr = lsock.accept()
    threading.Thread(target=handle, args=(conn, addr), daemon=True).start()
```

- `daemon=True`：主程式結束時不用等這些 thread
- 同一個 socket 可以一條 thread 收、一條 thread 送（全雙工）
- 多條 thread 共用的資料要上鎖 → 見 [05-concurrency-models.md](05-concurrency-models.md)

## 11. 練習

1. 用 `makefile()` 寫一個 line-based echo server，用 `nc` 測試一次貼上多行文字
2. 寫一個 client，連到 `example.com:80`，手動送出 `GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n`，印出完整回應
3. 故意不設 `SO_REUSEADDR`，觀察 Python 會 raise 什麼 exception
